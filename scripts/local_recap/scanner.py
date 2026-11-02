"""Brain session scanning, incremental transcript parsing, git state, and canonical artifact collection."""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .cache import SessionTranscriptCache
from .lineage import (
    normalize_workspace_variants,
    query_antigravity_sqlite_metadata,
    reconstruct_fork_forest,
)


def ensure_git_exclude(workspace: Path, pattern: str = ".local-notes/") -> bool:
    """Ensure `pattern` is present in `<workspace>/.git/info/exclude`."""
    git_dir = workspace / ".git"
    if git_dir.is_file():
        raw = git_dir.read_text(encoding="utf-8", errors="ignore").strip()
        if raw.startswith("gitdir:"):
            git_dir = (workspace / raw.split(":", 1)[1].strip()).resolve()
    exclude_file = git_dir / "info" / "exclude"
    if not exclude_file.parent.exists():
        return False
    existing = ""
    if exclude_file.exists():
        existing = exclude_file.read_text(encoding="utf-8", errors="ignore")
    lines = [line.strip() for line in existing.splitlines()]
    if pattern not in lines and pattern.rstrip("/") not in lines:
        with exclude_file.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"# Local session recaps & visualizations (local-recap skill)\n{pattern}\n")
        return True
    return False


def run_git(workspace: Path, args: list[str]) -> str:
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        return res.stdout.strip() if res.returncode == 0 else ""
    except Exception:
        return ""


def collect_git_state(workspace: Path) -> dict[str, Any]:
    current_branch = run_git(workspace, ["rev-parse", "--abbrev-ref", "HEAD"]) or "detached"
    branches_raw = run_git(
        workspace,
        ["for-each-ref", "--format=%(refname:short)|%(objectname:short)|%(contents:subject)", "refs/heads/"],
    )
    branches = []
    for line in branches_raw.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            branches.append({"name": parts[0], "sha": parts[1], "subject": parts[2]})

    commits_raw = run_git(
        workspace,
        ["log", "--all", "--date=short", "--pretty=format:%h|%ad|%d|%s", "-n", "12"],
    )
    commits = []
    for line in commits_raw.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append(
                {
                    "sha": parts[0],
                    "date": parts[1],
                    "refs": parts[2].strip(),
                    "subject": parts[3],
                }
            )
    status = run_git(workspace, ["status", "-s"])
    return {
        "current_branch": current_branch,
        "branches": branches,
        "commits": commits,
        "status": status,
    }


def extract_user_request_text(content: str) -> str:
    m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, flags=re.DOTALL)
    text = m.group(1).strip() if m else content.strip()
    return text


def utc_iso_to_local_str(iso_str: str, include_seconds: bool = False) -> str:
    """Convert an ISO-8601 timestamp (e.g. `2026-10-26T17:48:32Z`) to local wall-clock time."""
    if not iso_str:
        return ""
    try:
        cleaned = iso_str.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(cleaned)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        fmt = "%Y-%m-%d %H:%M:%S" if include_seconds else "%Y-%m-%d %H:%M"
        return parsed.strftime(fmt)
    except Exception:
        return iso_str[:19].replace("T", " ")


def format_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000.0:.1f}k"
    return str(n)


def _parse_transcript_metrics(raw_text: str) -> dict[str, Any]:
    """Parse step counts, token telemetry, user prompts, and authored markdown writes from `transcript.jsonl`."""
    user_prompts: list[dict[str, Any]] = []
    authored_writes: list[tuple[str, str]] = []  # (bname, created_at)
    first_ts_iso = ""
    last_ts_iso = ""
    first_step: int | None = None
    last_step: int | None = None
    step_timestamps: dict[int, str] = {}
    step_end_tokens: dict[int, int] = {}
    first_planner_ctx_tokens = 0
    user_chat_count = 0
    current_ctx_tokens = 0
    peak_ctx_tokens = 0
    total_output_tokens = 0
    compaction_count = 0
    prev_ctx = 0
    last_known_end_tokens = 0

    for line in raw_text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        created_at = str(obj.get("created_at") or "")
        s_idx = obj.get("step_index")
        if isinstance(s_idx, int):
            if first_step is None:
                first_step = s_idx
            last_step = s_idx
            if created_at:
                step_timestamps[s_idx] = created_at
        if created_at:
            if not first_ts_iso:
                first_ts_iso = created_at
            last_ts_iso = created_at

        in_tok = int(obj.get("input_tokens") or 0)
        cache_tok = int(obj.get("cache_read_tokens") or 0)
        out_tok = int(obj.get("output_tokens") or 0)
        total_output_tokens += out_tok
        ctx_tok = in_tok + cache_tok
        if ctx_tok > 0:
            if first_planner_ctx_tokens == 0:
                first_planner_ctx_tokens = ctx_tok
            last_known_end_tokens = ctx_tok + out_tok
            if prev_ctx > 60000 and ctx_tok < prev_ctx * 0.5:
                compaction_count += 1
            prev_ctx = ctx_tok
            current_ctx_tokens = ctx_tok
            if ctx_tok > peak_ctx_tokens:
                peak_ctx_tokens = ctx_tok
        if isinstance(s_idx, int) and last_known_end_tokens > 0:
            step_end_tokens[s_idx] = last_known_end_tokens

        if obj.get("type") == "USER_INPUT" and obj.get("content"):
            user_chat_count += 1
            req = extract_user_request_text(str(obj["content"]))
            if req and not req.startswith("<CONTEXT_SUMMARY>"):
                user_prompts.append(
                    {
                        "step": s_idx if s_idx is not None else -1,
                        "timestamp": utc_iso_to_local_str(created_at, include_seconds=False),
                        "text": req[:220] + ("..." if len(req) > 220 else ""),
                    }
                )
        for tc in obj.get("tool_calls") or []:
            tname = tc.get("name", "")
            if tname in {
                "write_file",
                "edit_file",
                "write_to_file",
                "replace_file_content",
                "multi_replace_file_content",
            }:
                args_obj = tc.get("args") or {}
                path_str = (
                    str(args_obj.get("Path") or args_obj.get("TargetFile") or "")
                    .strip('"')
                    .replace("\\", "/")
                )
                if path_str.lower().endswith(".md"):
                    bname = path_str.rsplit("/", 1)[-1]
                    if bname not in {"PROJECT_HUB.md", "INDEX.md", "README.md", "SKILL.md"}:
                        authored_writes.append((bname, created_at))

    return {
        "first_ts_iso": first_ts_iso,
        "last_ts_iso": last_ts_iso,
        "first_step": first_step,
        "last_step": last_step,
        "step_timestamps": step_timestamps,
        "step_end_tokens": step_end_tokens,
        "first_planner_ctx_tokens": first_planner_ctx_tokens,
        "user_chat_count": user_chat_count,
        "current_ctx_tokens": current_ctx_tokens,
        "peak_ctx_tokens": peak_ctx_tokens,
        "total_output_tokens": total_output_tokens,
        "compaction_count": compaction_count,
        "user_prompts": user_prompts[-8:],
        "authored_writes": authored_writes,
        "raw_head_snippet": raw_text[:12000],
    }


def scan_brain_sessions(
    brain_dir: Path | str,
    workspace: Path | str,
    cache_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    """Scan all `brain/*` directories for sessions matching `workspace`, extract full telemetry
    (using `SessionTranscriptCache` for unchanged transcripts), and reconstruct the Multi-Root Fork Forest.
    """
    brain_dir = Path(brain_dir)
    workspace = Path(workspace)
    if not brain_dir.exists():
        return [], {}, {}

    ws_name = workspace.name.lower()
    ws_variants = normalize_workspace_variants(workspace)
    sqlite_meta = query_antigravity_sqlite_metadata(brain_dir.parent, workspace)
    has_sqlite_db = (brain_dir.parent / "conversation_summaries.db").exists()
    ws_path_patterns = [
        re.compile(rf"(?<![a-z0-9_/-]){re.escape(v)}(?![a-z0-9_.-])")
        for v in ws_variants
    ]
    ws_seg_pattern = re.compile(rf"/{re.escape(ws_name)}(?:/|[\"\'\s]|$)")

    cache = SessionTranscriptCache(cache_path)
    sessions: list[dict[str, Any]] = []
    origin_map: dict[str, tuple[str, str]] = {}  # md_name -> (earliest_ts, session_id)
    latest_write_ts: dict[str, str] = {}  # md_name -> latest write_file ISO timestamp

    for conv_dir in brain_dir.iterdir():
        if not conv_dir.is_dir():
            continue
        cid = conv_dir.name
        db_info = sqlite_meta.get(cid, {})
        if db_info.get("known_other_workspace", False):
            continue
        transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
        top_files = [
            p
            for p in conv_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in {".md", ".png", ".svg", ".html"}
            and p.name != "PROJECT_HUB.md"
        ]
        matched = bool(db_info.get("matched_workspace", False))
        authored_docs: set[str] = set()
        parsed_metrics: dict[str, Any] | None = None

        if transcript.exists():
            cached = cache.get(cid, transcript)
            if cached is not None:
                if not matched:
                    head_low = str(cached.get("raw_head_snippet") or "").replace("\\", "/").lower()
                    if any(pat.search(head_low) for pat in ws_path_patterns):
                        matched = True
                    elif not has_sqlite_db and bool(cached.get("full_text_ws_match_for", {}).get(ws_name)):
                        matched = True
                if matched:
                    parsed_metrics = cached
            else:
                try:
                    raw_text = transcript.read_text(encoding="utf-8", errors="ignore")
                    raw_head_snippet = raw_text[:12000]
                    if not matched:
                        head_low = raw_head_snippet.replace("\\", "/").lower()
                        if any(pat.search(head_low) for pat in ws_path_patterns):
                            matched = True
                        elif not has_sqlite_db:
                            full_low = raw_text.replace("\\", "/").lower()
                            if any(pat.search(full_low) for pat in ws_path_patterns) or ws_seg_pattern.search(
                                full_low
                            ):
                                matched = True
                    if matched:
                        parsed_metrics = _parse_transcript_metrics(raw_text)
                        cache.put(cid, transcript, parsed_metrics)
                except Exception:
                    pass

        if not matched:
            continue

        m = parsed_metrics or {}
        first_ts_iso = str(m.get("first_ts_iso") or "")
        last_ts_iso = str(m.get("last_ts_iso") or "")
        first_step = m.get("first_step")
        last_step = m.get("last_step")
        step_timestamps = {int(k): v for k, v in (m.get("step_timestamps") or {}).items()}
        step_end_tokens = {int(k): int(v) for k, v in (m.get("step_end_tokens") or {}).items()}
        first_planner_ctx_tokens = int(m.get("first_planner_ctx_tokens") or 0)
        user_chat_count = int(m.get("user_chat_count") or 0)
        current_ctx_tokens = int(m.get("current_ctx_tokens") or 0)
        peak_ctx_tokens = int(m.get("peak_ctx_tokens") or 0)
        total_output_tokens = int(m.get("total_output_tokens") or 0)
        compaction_count = int(m.get("compaction_count") or 0)
        user_prompts = list(m.get("user_prompts") or [])
        raw_head_snippet = str(m.get("raw_head_snippet") or "")

        for bname, created_at in m.get("authored_writes") or []:
            authored_docs.add(bname)
            prev = origin_map.get(bname)
            if prev is None or (created_at and created_at < prev[0]):
                origin_map[bname] = (created_at or "9999", cid)
            prev_w = latest_write_ts.get(bname, "")
            if created_at and created_at > prev_w:
                latest_write_ts[bname] = created_at

        for p in top_files:
            if p.suffix.lower() == ".md" and p.name not in {"PROJECT_HUB.md", "INDEX.md"}:
                meta_f = p.parent / f"{p.name}.metadata.json"
                foreign_origin = False
                if meta_f.exists():
                    try:
                        m_orig = str(
                            json.loads(meta_f.read_text(encoding="utf-8", errors="ignore")).get(
                                "originSession"
                            )
                            or ""
                        )
                        if m_orig and m_orig != cid:
                            foreign_origin = True
                    except Exception:
                        pass
                if not foreign_origin:
                    authored_docs.add(p.name)
                    if p.name not in origin_map:
                        p_iso = dt.datetime.fromtimestamp(
                            p.stat().st_mtime, tz=dt.timezone.utc
                        ).isoformat()
                        origin_map[p.name] = (p_iso, cid)

        mtime = conv_dir.stat().st_mtime
        if not last_ts_iso:
            last_ts_iso = dt.datetime.fromtimestamp(mtime, tz=dt.timezone.utc).isoformat()
        if not first_ts_iso:
            first_ts_iso = last_ts_iso

        sessions.append(
            {
                "id": cid,
                "title": db_info.get("title") or "",
                "path": conv_dir,
                "first_ts_iso": first_ts_iso,
                "last_ts_iso": last_ts_iso,
                "started_local": utc_iso_to_local_str(first_ts_iso, include_seconds=False),
                "last_active": utc_iso_to_local_str(last_ts_iso, include_seconds=False),
                "mtime": mtime,
                "first_step": first_step if first_step is not None else 0,
                "last_step": last_step if last_step is not None else 0,
                "step_timestamps": step_timestamps,
                "step_end_tokens": step_end_tokens,
                "first_planner_ctx_tokens": first_planner_ctx_tokens,
                "user_chats": user_chat_count,
                "current_ctx_tokens": current_ctx_tokens,
                "peak_ctx_tokens": peak_ctx_tokens,
                "total_output_tokens": total_output_tokens,
                "compaction_count": compaction_count,
                "prompts": user_prompts[-8:],
                "artifacts": top_files,
                "authored_docs": sorted(authored_docs),
                "raw_head_snippet": raw_head_snippet,
                "db_ancestry": db_info.get("ancestry") or [],
                "subagent_parent_id": db_info.get("subagent_parent_id") or "",
                "agent_name": db_info.get("agent_name") or "",
                "nesting_depth": int(db_info.get("nesting_depth") or 0),
                "is_subagent": bool(
                    db_info.get("subagent_parent_id") or int(db_info.get("nesting_depth") or 0) > 0
                ),
                "parent_id": None,
                "root_id": cid,
                "fork_depth": 0,
                "fork_step": None,
                "lineage_source": "root",
            }
        )

    cache.save()
    reconstruct_fork_forest(sessions)
    sessions.sort(key=lambda s: s["last_ts_iso"], reverse=True)
    clean_origin = {k: v[1] for k, v in origin_map.items()}
    clean_ts = {k: utc_iso_to_local_str(v, include_seconds=False) for k, v in latest_write_ts.items()}
    return sessions, clean_origin, clean_ts


def extract_md_title(md_path: Path) -> str:
    try:
        for line in md_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:
        pass
    return md_path.stem.replace("_", " ").title()


def classify_document(
    md_name: str, title: str, content: str, meta_summary: str = ""
) -> tuple[int, str, str]:
    """Condense all notes into 3 high-level categories:
    1. `📋 Recap`
    2. `📘 Deep Dive`
    3. `📐 Spec & Plan`
    """
    low = md_name.lower()
    if "recap" in low or "summary" in low or "status" in low or "changelog" in low:
        prio, cat = 1, "📋 Recap"
    elif any(k in low for k in ("briefing", "proposal", "plan", "spec", "roadmap", "rfc", "design")):
        prio, cat = 3, "📐 Spec & Plan"
    else:
        prio, cat = 2, "📘 Deep Dive"

    clean_meta = " ".join(meta_summary.splitlines()).strip()
    if clean_meta and not clean_meta.lower().startswith("synced from session"):
        if len(clean_meta) > 145:
            clean_meta = clean_meta[:142] + "..."
        return (prio, cat, clean_meta)

    first_para = ""
    for line in content.splitlines():
        s = line.strip()
        if s and not s.startswith(("#", "-", "*", "|", "!", "`", "---")):
            s = re.sub(r"^>\s*(\[![A-Z]+\])?\s*", "", s).strip()
            s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
            s = s.replace("**", "").replace("*", "")
            if len(s) > 20:
                first_para = s
                break
    if not first_para:
        first_para = title
    if len(first_para) > 145:
        first_para = first_para[:142] + "..."
    return (prio, cat, first_para)


def extract_md_sections_and_stats(content: str) -> dict[str, Any]:
    lines = content.splitlines()
    h2s: list[str] = []
    img_count = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", content))
    mermaid_count = len(re.findall(r"```mermaid", content))
    for line in lines:
        if line.startswith("## "):
            sec = line[3:].strip()
            sec = re.sub(r"^(Part\s+\d+:\s*|\d+\.\s*)", "", sec)
            sec = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", sec)
            sec = sec.replace("`", "").replace("*", "")
            sec = re.sub(r"\s*\([^)]*\)\s*$", "", sec).strip()
            if ":" in sec and len(sec) > 36:
                sec = sec.split(":", 1)[0].strip()
            h2s.append(sec)
    return {
        "line_count": len(lines),
        "h2s": h2s[:4],
        "total_h2s": len(h2s),
        "visual_count": img_count + mermaid_count,
    }


def collect_canonical_artifacts(
    sessions: list[dict[str, Any]],
    origin_map: dict[str, str],
    authored_ts_map: dict[str, str],
    local_notes_dir: Path,
    workspace: Path,
) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    """Gather the newest version of every image and Markdown note across all `brain/*`
    sessions (and any legacy physical files in `<workspace>/.local-notes/`).
    """
    canonical_images: dict[str, Path] = {}
    canonical_mds: dict[str, dict[str, Any]] = {}

    for img_dir in (workspace / "docs" / "assets", local_notes_dir / "assets"):
        if img_dir.exists() and not img_dir.is_symlink():
            for img in img_dir.iterdir():
                if img.is_file() and not img.is_symlink() and img.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg"}:
                    canonical_images[img.name] = img

    def _consider_md(md_path: Path, fallback_sid: str, is_local_backup: bool = False) -> None:
        if md_path.is_symlink() or md_path.name in {"PROJECT_HUB.md", "INDEX.md"}:
            return
        meta_file = md_path.parent / f"{md_path.name}.metadata.json"
        meta_summary = ""
        meta_origin = ""
        if meta_file.exists():
            try:
                mobj = json.loads(meta_file.read_text(encoding="utf-8", errors="ignore"))
                meta_summary = str(mobj.get("summary") or "")
                meta_origin = str(mobj.get("originSession") or "")
            except Exception:
                pass

        if (
            not is_local_backup
            and meta_origin
            and meta_origin != fallback_sid
            and (md_path.parent.parent / meta_origin / md_path.name).exists()
        ):
            return

        mtime = md_path.stat().st_mtime
        existing = canonical_mds.get(md_path.name)
        if existing is not None:
            if is_local_backup and not existing.get("from_local_backup", False):
                return
            if existing["mtime"] >= mtime:
                return

        raw_content = md_path.read_text(encoding="utf-8", errors="ignore")
        title = extract_md_title(md_path)
        prio, category, purpose = classify_document(md_path.name, title, raw_content, meta_summary)
        stats = extract_md_sections_and_stats(raw_content)
        if is_local_backup:
            true_origin = origin_map.get(md_path.name) or meta_origin or fallback_sid
            brain_root = sessions[0]["path"].parent if sessions else md_path.parent
            orig_brain_path = brain_root / true_origin / md_path.name
        else:
            true_origin = meta_origin or fallback_sid or origin_map.get(md_path.name, "")
            orig_candidate = md_path.parent.parent / true_origin / md_path.name if true_origin else md_path
            orig_brain_path = orig_candidate if orig_candidate.exists() else md_path
        true_ts = authored_ts_map.get(md_path.name) or dt.datetime.fromtimestamp(mtime).strftime(
            "%Y-%m-%d %H:%M"
        )

        canonical_mds[md_path.name] = {
            "name": md_path.name,
            "path": md_path,
            "brain_path": orig_brain_path,
            "from_local_backup": is_local_backup,
            "mtime": mtime,
            "updated_str": true_ts,
            "title": title,
            "priority": prio,
            "category": category,
            "purpose": purpose,
            "summary": meta_summary or purpose,
            "origin_sid": true_origin,
            "stats": stats,
        }

    for sess in sessions:
        for art in sess["artifacts"]:
            if art.is_symlink():
                continue
            ext = art.suffix.lower()
            if ext in {".png", ".svg", ".jpg", ".jpeg"}:
                prev_img = canonical_images.get(art.name)
                if prev_img is None or art.stat().st_mtime > prev_img.stat().st_mtime:
                    canonical_images[art.name] = art
            elif ext == ".md":
                _consider_md(art, sess["id"], is_local_backup=False)

    default_sid = sessions[0]["id"] if sessions else "local"
    for legacy_dir in (local_notes_dir, local_notes_dir / "notes"):
        if legacy_dir.exists() and not legacy_dir.is_symlink():
            for local_md in legacy_dir.glob("*.md"):
                if not local_md.is_symlink():
                    _consider_md(local_md, origin_map.get(local_md.name, default_sid), is_local_backup=True)

    return canonical_images, canonical_mds


def sort_canonical_docs(canonical_mds: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministically sort canonical documents by category priority, newest timestamp/mtime, and filename."""
    docs = sorted(canonical_mds.values(), key=lambda d: d["name"])
    docs.sort(key=lambda d: (d.get("updated_str") or "", d.get("mtime") or 0.0), reverse=True)
    docs.sort(key=lambda d: d["priority"])
    return docs
