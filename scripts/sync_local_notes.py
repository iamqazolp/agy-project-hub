#!/usr/bin/env python3
"""Zero-context-overhead multi-session & fork synchronizer for Antigravity (`local-recap` skill).

Why this costs ~0 LLM context tokens:
- All transcript parsing (`transcript.jsonl`), fork-tree reconstruction, token/context accounting,
  and Markdown/HTML generation run in this standalone Python subprocess outside the LLM context window.

Key Features:
1. Bidirectional Artifact Sync (`brain/<id>/*.md` <-> `<workspace>/.local-notes/notes/*.md`):
   - Syncs all Markdown notes and visual assets across every session/fork of the project into each
     session's native `brain/<conversation-id>/` folder (with `.md.metadata.json`) so they open in
     Antigravity's native styled Artifact Viewer.
2. Automatic Fork Tree & Session Telemetry Detection:
   - Inspects `step_index` ranges and timestamps in `.system_generated/logs/transcript.jsonl` to
     detect Root sessions (`step 0`) vs. Forked sessions (`step K > 0`) and identify the exact
     Parent Session and fork step (`Fork of <parent> @ step K-1`).
   - Computes per-session **Current Context Usage** (`input_tokens + cache_read_tokens`),
     **Peak Context Usage**, **Total Output Tokens**, **User Chat Count**, **Step Range**, and
     **Local Start / Last Active Timestamps**.
3. Condensed 3-Category Knowledge Base Table (`📋 Recap`, `📘 Deep Dive`, `📐 Spec & Plan`)
   with true local authoring timestamps and full copyable/clickable Session IDs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any


def parse_parent_reference_blob(blob: bytes) -> tuple[str, int | None]:
    """Decode Antigravity's `parent_references.data` protobuf blob without external protobuf deps.

    Wire format in `conversations/<id>.db` -> `parent_references`:
      - Field 1 (`0x0a`, len 36): parent `trajectory_id` (UUID)
      - Field 2 (`0x10`, varint): exact `fork_step` index in parent
      - Field 6 (`0x32`, len 36): parent `cascade_id` / `session_id` (UUID)
    """
    parent_sid = ""
    fork_step: int | None = None
    i = 0
    n = len(blob)
    while i < n:
        tag = blob[i]
        i += 1
        field_num = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:  # varint
            val = 0
            shift = 0
            while i < n:
                b = blob[i]
                i += 1
                val |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            if field_num == 2:
                fork_step = val
        elif wire_type == 2:  # length-delimited
            length = 0
            shift = 0
            while i < n:
                b = blob[i]
                i += 1
                length |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            chunk = blob[i : i + length]
            i += length
            if field_num == 6 and len(chunk) == 36:
                parent_sid = chunk.decode("ascii", errors="ignore")
        elif wire_type == 1:
            i += 8
        elif wire_type == 5:
            i += 4
        else:
            break
    if not parent_sid:
        uuids = [u.decode("ascii", errors="ignore") for u in re.findall(rb"[0-9a-f-]{36}", blob)]
        if len(uuids) >= 2:
            parent_sid = uuids[-1]
    return parent_sid, fork_step


def query_antigravity_sqlite_metadata(
    ag_dir: Path, workspace: Path
) -> dict[str, dict[str, Any]]:
    """Read ground-truth workspace matching, titles, and exact fork lineage from Antigravity's
    SQLite databases (`conversation_summaries.db` and `conversations/<id>.db`).
    """
    meta: dict[str, dict[str, Any]] = {}
    ws_norm = str(workspace).replace("\\", "/").lower()
    ws_name = workspace.name.lower()

    summaries_db = ag_dir / "conversation_summaries.db"
    if summaries_db.exists():
        try:
            conn = sqlite3.connect(f"file:{summaries_db}?mode=ro", uri=True)
            rows = conn.execute(
                "SELECT conversation_id, title, step_count, workspace_uris, parent_conversation_id "
                "FROM conversation_summaries"
            ).fetchall()
            for cid, title, step_count, ws_uris, parent_cid in rows:
                uris_low = (ws_uris or "").replace("\\", "/").lower()
                if ws_norm in uris_low or ws_name in uris_low:
                    meta[cid] = {
                        "matched_workspace": True,
                        "title": (title or "").strip(),
                        "db_step_count": int(step_count or 0),
                        "subagent_parent_id": (parent_cid or "").strip(),
                        "ancestry": [],
                    }
            conn.close()
        except Exception:
            pass

    conv_dir = ag_dir / "conversations"
    if conv_dir.exists():
        for db_file in conv_dir.glob("*.db"):
            cid = db_file.stem
            if cid not in meta:
                continue
            try:
                conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
                prefs = conn.execute(
                    "SELECT idx, data FROM parent_references ORDER BY idx ASC"
                ).fetchall()
                ancestry: list[dict[str, Any]] = []
                for idx, blob in prefs:
                    if isinstance(blob, bytes):
                        psid, fstep = parse_parent_reference_blob(blob)
                        if psid:
                            ancestry.append({"idx": idx, "parent_id": psid, "fork_step": fstep})
                meta[cid]["ancestry"] = ancestry
                conn.close()
            except Exception:
                pass

    return meta


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


def scan_brain_sessions(
    brain_dir: Path, workspace: Path
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    """Scan all `brain/*` directories for sessions matching `workspace`, extract full telemetry
    (context tokens, chat counts, step indices, timestamps), and reconstruct the Multi-Root Fork Forest.
    """
    if not brain_dir.exists():
        return [], {}, {}
    ws_name = workspace.name.lower()
    ws_norm = str(workspace).replace("\\", "/").lower()
    sqlite_meta = query_antigravity_sqlite_metadata(brain_dir.parent, workspace)
    sessions: list[dict[str, Any]] = []
    origin_map: dict[str, tuple[str, str]] = {}  # md_name -> (earliest_ts, session_id)
    latest_write_ts: dict[str, str] = {}  # md_name -> latest write_file ISO timestamp

    for conv_dir in brain_dir.iterdir():
        if not conv_dir.is_dir():
            continue
        cid = conv_dir.name
        db_info = sqlite_meta.get(cid, {})
        transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
        top_files = [
            p
            for p in conv_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in {".md", ".png", ".svg", ".html"}
            and p.name != "PROJECT_HUB.md"
        ]
        matched = bool(db_info.get("matched_workspace", False))
        user_prompts: list[dict[str, str]] = []
        authored_docs: set[str] = set()
        first_ts_iso = ""
        last_ts_iso = ""
        first_step: int | None = None
        last_step: int | None = None
        step_timestamps: dict[int, str] = {}
        step_end_tokens: dict[int, int] = {}
        first_planner_ctx_tokens: int = 0
        user_chat_count = 0
        current_ctx_tokens = 0
        peak_ctx_tokens = 0
        total_output_tokens = 0
        compaction_count = 0
        prev_ctx = 0
        raw_head_snippet = ""

        for f in top_files:
            if f.suffix.lower() == ".md":
                try:
                    txt = f.read_text(encoding="utf-8", errors="ignore").lower()
                    if ws_name in txt or ws_norm in txt:
                        matched = True
                except Exception:
                    pass

        if transcript.exists():
            try:
                raw_text = transcript.read_text(encoding="utf-8", errors="ignore")
                raw_head_snippet = raw_text[:12000]
                if ws_name in raw_text.lower() or ws_norm in raw_text.lower():
                    matched = True
                if matched:
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
                            if isinstance(s_idx, int):
                                step_end_tokens[s_idx] = ctx_tok + out_tok
                            if prev_ctx > 60000 and ctx_tok < prev_ctx * 0.5:
                                compaction_count += 1
                            prev_ctx = ctx_tok
                            current_ctx_tokens = ctx_tok
                            if ctx_tok > peak_ctx_tokens:
                                peak_ctx_tokens = ctx_tok

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
                            if tname == "write_file":
                                args_obj = tc.get("args") or {}
                                path_str = str(args_obj.get("Path", "")).strip('"').replace("\\", "/")
                                if path_str.lower().endswith(".md"):
                                    bname = path_str.rsplit("/", 1)[-1]
                                    if bname not in {"PROJECT_HUB.md", "INDEX.md", "README.md", "SKILL.md"}:
                                        authored_docs.add(bname)
                                        prev = origin_map.get(bname)
                                        if prev is None or (created_at and created_at < prev[0]):
                                            origin_map[bname] = (created_at or "9999", cid)
                                        prev_w = latest_write_ts.get(bname, "")
                                        if created_at and created_at > prev_w:
                                            latest_write_ts[bname] = created_at
            except Exception:
                pass

        if matched:
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
                    "parent_id": None,
                    "root_id": cid,
                    "fork_depth": 0,
                    "fork_step": None,
                    "lineage_source": "root",
                }
            )

    # Reconstruct Multi-Root Fork Forest (`parent_id`, `root_id`, `fork_depth`, `fork_step`)
    sess_by_id = {s["id"]: s for s in sessions}
    all_ids = list(sess_by_id.keys())
    for s in sessions:
        ancestry = s.get("db_ancestry") or []
        fstep = s["first_step"]

        # Stage 1 (Ground Truth): SQLite `conversations/<id>.db -> parent_references` protobuf chain
        if ancestry:
            immediate = ancestry[-1]
            s["parent_id"] = immediate["parent_id"]
            s["fork_step"] = (
                immediate["fork_step"]
                if immediate["fork_step"] is not None
                else (fstep - 1 if fstep and fstep > 0 else 0)
            )
            s["root_id"] = ancestry[0]["parent_id"]
            s["fork_depth"] = len(ancestry)
            s["lineage_source"] = "sqlite_parent_references"
            continue

        if fstep is None or fstep <= 0:
            s["parent_id"] = None
            s["fork_step"] = None
            s["root_id"] = s["id"]
            s["fork_depth"] = 0
            s["lineage_source"] = "root"
            continue

        fork_point = fstep - 1
        s["fork_step"] = fork_point
        best_parent = None

        # Stage 2 (Fallback): Check if another session ID is explicitly mentioned in the opening context
        for cand_id in all_ids:
            if cand_id != s["id"] and cand_id in s["raw_head_snippet"]:
                best_parent = cand_id
                s["lineage_source"] = "transcript_context_uuid"
                break

        # Stage 3 (Fallback): Match by step-boundary token fingerprint (`ctx + out` at `fork_point`
        # vs child's `first_planner_ctx_tokens`) + chronological timestamp proximity
        if best_parent is None:
            scored_candidates = []
            child_open_ctx = s["first_planner_ctx_tokens"]
            for cand in sessions:
                if cand["id"] == s["id"]:
                    continue
                if cand["first_step"] <= fork_point <= cand["last_step"]:
                    step_ts = cand["step_timestamps"].get(fork_point, cand["first_ts_iso"])
                    if step_ts <= s["first_ts_iso"]:
                        parent_end_tok = cand["step_end_tokens"].get(fork_point, 0)
                        tok_diff = (
                            abs(child_open_ctx - parent_end_tok)
                            if (child_open_ctx > 0 and parent_end_tok > 0)
                            else 999999999
                        )
                        scored_candidates.append((tok_diff, -cand["first_step"], step_ts, cand["id"]))
            if scored_candidates:
                scored_candidates.sort(key=lambda x: (x[0], x[1]))
                best_parent = scored_candidates[0][3]
                s["lineage_source"] = "token_timestamp_fingerprint"

        s["parent_id"] = best_parent

    # Resolve `root_id` and `fork_depth` for any fallback-matched sessions & assign Root Tree numbers
    for s in sessions:
        if s["parent_id"] and s["fork_depth"] == 0:
            depth = 0
            cur = s["parent_id"]
            visited = {s["id"]}
            while cur and cur not in visited:
                visited.add(cur)
                depth += 1
                parent_obj = sess_by_id.get(cur)
                if parent_obj and parent_obj["parent_id"]:
                    cur = parent_obj["parent_id"]
                else:
                    break
            s["root_id"] = cur or s["id"]
            s["fork_depth"] = depth

    # Number Root Trees chronologically (`Root Tree #1`, `Root Tree #2`, ...)
    root_sessions = sorted(
        [s for s in sessions if not s["parent_id"]],
        key=lambda r: r["first_ts_iso"],
    )
    root_tree_map = {r["id"]: idx + 1 for idx, r in enumerate(root_sessions)}
    for s in sessions:
        if s["root_id"] not in root_tree_map:
            root_tree_map[s["root_id"]] = len(root_tree_map) + 1
        s["tree_num"] = root_tree_map[s["root_id"]]

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

    # Extract a clean 1-sentence purpose from metadata summary, first paragraph, or H1 title
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


def write_artifact_metadata(md_file: Path, summary: str, origin_sid: str = "") -> None:
    """Write companion `<name>.md.metadata.json` so Antigravity renders `md_file` natively."""
    meta_path = md_file.parent / f"{md_file.name}.metadata.json"
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f0Z")
    payload: dict[str, Any] = {
        "summary": summary,
        "updatedAt": now_iso,
        "userFacing": True,
    }
    if origin_sid:
        payload["originSession"] = origin_sid
    meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")


def rewrite_md_images_for_brain_dir(md_text: str, target_brain_dir: Path) -> str:
    """Rewrite any embedded image path (`.../brain/<any-id>/<img.png>` or `../assets/<img.png>`)
    to the exact absolute path inside `target_brain_dir`.
    """
    target_norm = str(target_brain_dir).replace("\\", "/")
    pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

    def _repl(match: re.Match[str]) -> str:
        alt = match.group(1)
        url = match.group(2).strip()
        clean_url = url.replace("\\", "/")
        if clean_url.lower().endswith((".png", ".svg", ".jpg", ".jpeg")):
            basename = clean_url.rsplit("/", 1)[-1]
            if (target_brain_dir / basename).exists():
                return f"![{alt}]({target_norm}/{basename})"
        return match.group(0)

    return pattern.sub(_repl, md_text)


def rewrite_markdown_image_paths_relative(md_text: str, assets_rel_prefix: str) -> str:
    """Rewrite absolute brain image links to local relative asset paths for `.local-notes/`."""
    pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

    def _repl(match: re.Match[str]) -> str:
        alt = match.group(1)
        url = match.group(2).strip()
        clean_url = url.replace("\\", "/")
        if ("/brain/" in clean_url or "assets/" in clean_url) and clean_url.lower().endswith(
            (".png", ".svg", ".jpg", ".jpeg")
        ):
            basename = clean_url.rsplit("/", 1)[-1]
            return f"![{alt}]({assets_rel_prefix}/{basename})"
        return match.group(0)

    return pattern.sub(_repl, md_text)


def collect_canonical_artifacts(
    sessions: list[dict[str, Any]],
    origin_map: dict[str, str],
    authored_ts_map: dict[str, str],
    notes_dir: Path,
    assets_dir: Path,
    workspace: Path,
) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    """Gather the newest version of every image and Markdown note across BOTH all `brain/*`
    sessions AND `<workspace>/.local-notes/notes/`.
    """
    canonical_images: dict[str, Path] = {}
    canonical_mds: dict[str, dict[str, Any]] = {}

    for img_dir in (workspace / "docs" / "assets", assets_dir):
        if img_dir.exists():
            for img in img_dir.iterdir():
                if img.is_file() and img.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg"}:
                    canonical_images[img.name] = img

    def _consider_md(md_path: Path, fallback_sid: str) -> None:
        if md_path.name in {"PROJECT_HUB.md", "INDEX.md"}:
            return
        mtime = md_path.stat().st_mtime
        existing = canonical_mds.get(md_path.name)
        if existing is not None and existing["mtime"] >= mtime:
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

        raw_content = md_path.read_text(encoding="utf-8", errors="ignore")
        title = extract_md_title(md_path)
        prio, category, purpose = classify_document(md_path.name, title, raw_content, meta_summary)
        stats = extract_md_sections_and_stats(raw_content)
        true_origin = origin_map.get(md_path.name) or meta_origin or fallback_sid
        true_ts = authored_ts_map.get(md_path.name) or dt.datetime.fromtimestamp(mtime).strftime(
            "%Y-%m-%d %H:%M"
        )

        canonical_mds[md_path.name] = {
            "name": md_path.name,
            "path": md_path,
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
            ext = art.suffix.lower()
            if ext in {".png", ".svg", ".jpg", ".jpeg"}:
                prev_img = canonical_images.get(art.name)
                if prev_img is None or art.stat().st_mtime > prev_img.stat().st_mtime:
                    canonical_images[art.name] = art
            elif ext == ".md":
                _consider_md(art, sess["id"])

    default_sid = sessions[0]["id"] if sessions else "local"
    if notes_dir.exists():
        for local_md in notes_dir.glob("*.md"):
            _consider_md(local_md, origin_map.get(local_md.name, default_sid))

    return canonical_images, canonical_mds


def sync_all_targets(
    sessions: list[dict[str, Any]],
    canonical_images: dict[str, Path],
    canonical_mds: dict[str, dict[str, Any]],
    workspace: Path,
    git_state: dict[str, Any],
    target_session_ids: list[str],
    brain_dir: Path,
    notes_dir: Path,
    assets_dir: Path,
) -> list[Path]:
    """Sync canonical images and Markdown artifacts into every target session's `brain/<id>/`
    folder AND `<workspace>/.local-notes/notes/`, then generate `PROJECT_HUB.md`.
    """
    for img_name, src_img in canonical_images.items():
        dst_asset = assets_dir / img_name
        if src_img.resolve() != dst_asset.resolve():
            shutil.copy2(src_img, dst_asset)

    sorted_docs = sorted(
        canonical_mds.values(),
        key=lambda d: (d["priority"], d["updated_str"] == "", d["name"]),
    )
    sorted_docs.sort(key=lambda d: d["updated_str"], reverse=True)
    sorted_docs.sort(key=lambda d: d["priority"])

    for doc in sorted_docs:
        raw_txt = doc["path"].read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
        rel_txt = rewrite_markdown_image_paths_relative(raw_txt, "../assets")
        (notes_dir / doc["name"]).write_text(rel_txt, encoding="utf-8", newline="\n")

    generated_hubs: list[Path] = []
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur_branch = git_state["current_branch"]

    # Sort sessions chronologically by start time for the Fork Tree diagram, and by last_active for table
    sessions_by_start = sorted(sessions, key=lambda s: (s["first_step"], s["first_ts_iso"]))
    session_num_map = {s["id"]: i + 1 for i, s in enumerate(sessions_by_start)}

    for sid in target_session_ids:
        tdir = brain_dir / sid
        if not tdir.exists():
            continue
        tdir_norm = str(tdir).replace("\\", "/")

        for img_name, src_img in canonical_images.items():
            dst_img = tdir / img_name
            if src_img.resolve() != dst_img.resolve():
                shutil.copy2(src_img, dst_img)

        for doc in sorted_docs:
            dst_md = tdir / doc["name"]
            raw_txt = doc["path"].read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
            rewritten_txt = rewrite_md_images_for_brain_dir(raw_txt, tdir)
            dst_md.write_text(rewritten_txt, encoding="utf-8", newline="\n")
            write_artifact_metadata(dst_md, doc["purpose"], doc["origin_sid"])

        hub_lines = [
            f"# ⚡ `{workspace.name}` — Multi-Session & Fork Command Center",
            "",
            "> [!TIP]",
            f"> **Zero-Context-Overhead Sync:** All {len(sorted_docs)} project guides and {len(sessions)} session/fork logs are synced into this session's native artifact folder (`{sid}`) by an external Python script (`0` LLM tokens used). Click any document below to open it in **Antigravity's native styled Artifact Viewer**.",
            "",
            "---",
            "",
            f"## 1. Synced Project Knowledge Base ({len(sorted_docs)} Native Artifacts)",
            "",
            "| Category | Timestamp | Document (Click for Native View) | Summary & Purpose | Key Sections | Origin Session (Full ID) |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for doc in sorted_docs:
            md_name = doc["name"]
            cat = doc["category"]
            purpose = doc["purpose"]
            st = doc["stats"]
            h2_badges = " · ".join(f"`{h}`" for h in st["h2s"]) if st["h2s"] else "—"
            vis_str = f" · `{st['visual_count']} visuals`" if st["visual_count"] > 0 else ""
            orig_full = doc["origin_sid"]
            orig_link = f"[`{orig_full}`](conversation://{orig_full})"
            scope_col = f"{orig_link} (`{st['line_count']} lines`{vis_str})"
            doc_col = f"[**`{md_name}`**](file:///{tdir_norm}/{md_name})"
            hub_lines.append(
                f"| **{cat}** | `{doc['updated_str']}` | {doc_col} | {purpose} | {h2_badges} | {scope_col} |"
            )

        root_count = len({s["root_id"] for s in sessions})
        hub_lines.extend(
            [
                "",
                "---",
                "",
                f"## 2. Session & Fork Telemetry ({len(sessions)} Sessions across {root_count} Root Tree{'s' if root_count != 1 else ''})",
                "",
                "| Tree & Fork Lineage | Full Session ID (Click to Open / Copy to Resume) | Context Usage (Active / Peak) | Chats & Steps | Started -> Last Active | Authored Docs |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )

        for s in sessions:
            s_id = s["id"]
            t_num = s.get("tree_num", 1)
            f_depth = s.get("fork_depth", 0)
            title_tag = f" *({s['title']})*" if s.get("title") else ""
            is_cur = " **(CURRENT)**" if s_id == sid else ""
            if s["parent_id"]:
                lineage = (
                    f"`Tree #{t_num}` · 🔀 **Fork (d={f_depth})** of `{s['parent_id'][:8]}` "
                    f"@ `step {s['fork_step']}`{title_tag}{is_cur}"
                )
            else:
                lineage = f"`Tree #{t_num}` · 🌱 **Root Session** (`step 0`){title_tag}{is_cur}"

            id_cell = f"[`{s_id}`](conversation://{s_id})"
            cur_ctx = format_tokens(s["current_ctx_tokens"])
            peak_ctx = format_tokens(s["peak_ctx_tokens"])
            out_tok = format_tokens(s["total_output_tokens"])
            compact_note = f" (`{s['compaction_count']}x compacted`)" if s["compaction_count"] > 0 else ""
            ctx_cell = f"**`{cur_ctx}`** active / `{peak_ctx}` peak{compact_note} · `{out_tok}` out"

            step_span = s["last_step"] - s["first_step"] + 1
            chats_cell = f"**`{s['user_chats']} chats`** · `{step_span} steps` (`#{s['first_step']}..#{s['last_step']}`)"
            time_cell = f"`{s['started_local']}` -> `{s['last_active']}`"

            valid_authored = [a for a in (s.get("authored_docs") or []) if a in canonical_mds]
            docs_cell = (
                " · ".join(f"[`{a}`](file:///{tdir_norm}/{a})" for a in valid_authored)
                if valid_authored
                else "—"
            )
            hub_lines.append(
                f"| {lineage} | {id_cell} | {ctx_cell} | {chats_cell} | {time_cell} | {docs_cell} |"
            )

        hub_lines.extend(
            [
                "",
                "### Multi-Root Session Fork Forest (`mermaid`)",
                "",
                "```mermaid",
                "flowchart LR",
            ]
        )
        # Group sessions by `tree_num` so multiple root sessions render as distinct subgraphs
        trees: dict[int, list[dict[str, Any]]] = {}
        for s in sessions_by_start:
            t_num = s.get("tree_num", 1)
            trees.setdefault(t_num, []).append(s)

        for t_num in sorted(trees.keys()):
            tree_sessions = trees[t_num]
            root_sess = next((x for x in tree_sessions if not x["parent_id"]), tree_sessions[0])
            r_short = root_sess["id"][:8]
            r_title = f" - {root_sess['title']}" if root_sess.get("title") else ""
            hub_lines.append(f'    subgraph T{t_num}["Tree #{t_num} (Root: {r_short}{r_title})"]')
            for s in tree_sessions:
                num = session_num_map[s["id"]]
                s_short = s["id"][:8]
                cur_tag = " [CURRENT]" if s["id"] == sid else ""
                ctx_lbl = format_tokens(s["current_ctx_tokens"])
                peak_lbl = format_tokens(s["peak_ctx_tokens"])
                f_depth = s.get("fork_depth", 0)
                role_lbl = "Root" if not s["parent_id"] else f"Fork d={f_depth} @{s['fork_step']}"
                u_chats = s["user_chats"]
                f_step = s["first_step"]
                l_step = s["last_step"]
                hub_lines.append(
                    f'        N{num}["S{num}: {s_short}{cur_tag} ({role_lbl}) | {u_chats} chats, steps {f_step}..{l_step} | Ctx: {ctx_lbl} (peak {peak_lbl})"]'
                )
            for s in tree_sessions:
                num = session_num_map[s["id"]]
                if s["parent_id"] and s["parent_id"] in session_num_map:
                    pnum = session_num_map[s["parent_id"]]
                    fk_step = s["fork_step"]
                    hub_lines.append(f'        N{pnum} -- "forked @ step {fk_step}" --> N{num}')
            hub_lines.append("    end")

        hub_lines.extend(
            [
                "```",
                "",
                "---",
                "",
                "## 3. Recent Prompts Per Session / Fork",
                "",
            ]
        )
        for s in sessions:
            s_id = s["id"]
            is_cur_badge = " *(Current Session)*" if s_id == sid else ""
            role_badge = (
                f"Fork of `{s['parent_id']}` @ step `{s['fork_step']}`"
                if s["parent_id"]
                else "Root Session (`step 0`)"
            )
            hub_lines.append(
                f"### [`{s_id}`](conversation://{s_id}){is_cur_badge}"
            )
            hub_lines.append(
                f"- **Lineage:** {role_badge} · **Context:** `{format_tokens(s['current_ctx_tokens'])}` active (`{format_tokens(s['peak_ctx_tokens'])}` peak) · **Chats:** `{s['user_chats']}` (`steps #{s['first_step']}..#{s['last_step']}`) · **Active:** `{s['started_local']}` -> `{s['last_active']}`"
            )
            if s["prompts"]:
                for pr in s["prompts"][-5:]:
                    one_line = " ".join(pr["text"].splitlines())
                    hub_lines.append(f"  - **`[{pr['timestamp']} · step #{pr['step']}]`** {one_line}")
            hub_lines.append("")

        hub_lines.extend(
            [
                "---",
                "",
                "## 4. Git Branches & Tip Commits",
                "",
                "| Branch | Tip Commit | Subject |",
                "| :--- | :--- | :--- |",
            ]
        )
        for b in git_state["branches"]:
            marker = " **(active)**" if b["name"] == git_state["current_branch"] else ""
            hub_lines.append(f"| `{b['name']}`{marker} | `{b['sha']}` | {b['subject']} |")

        hub_lines.extend(
            [
                "",
                f"*Last synced by `local-recap` skill at `{now_str}`.*",
                "",
            ]
        )

        hub_path = tdir / "PROJECT_HUB.md"
        hub_path.write_text("\n".join(hub_lines), encoding="utf-8", newline="\n")
        write_artifact_metadata(
            hub_path,
            f"Unified Native Antigravity Command Center for {workspace.name} ({len(sorted_docs)} synced artifacts, fork tree, and session telemetry across {len(sessions)} sessions).",
            sid,
        )
        generated_hubs.append(hub_path)

    return generated_hubs


def update_local_index_md_with_native_links(
    local_notes_dir: Path,
    workspace: Path,
    git_state: dict[str, Any],
    sorted_docs: list[dict[str, Any]],
    viz_dir: Path,
    primary_brain_dir: Path,
    sessions: list[dict[str, Any]],
) -> Path:
    """Write `<workspace>/.local-notes/INDEX.md` with categorized direct links to the native
    brain artifacts and full session IDs / fork telemetry.
    """
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    brain_norm = str(primary_brain_dir).replace("\\", "/")
    viz_files = sorted(viz_dir.glob("*.html"), key=lambda p: p.name)

    lines = [
        f"# `{workspace.name}` — Local Multi-Session & Fork Launcher",
        "",
        f"> **Synced:** `{now_str}` | **Active Branch:** `{git_state['current_branch']}` | **Artifacts:** `{len(sorted_docs)}` | **Sessions/Forks:** `{len(sessions)}`",
        "> **How to open in Antigravity's Native Styled Viewer:** `Ctrl+Click` any link in the **Native Antigravity Viewer Link** column below.",
        "",
        "---",
        "",
        "## 1. Synced Project Knowledge Base",
        "",
        "| Category | Timestamp | Native Antigravity Viewer Link (Rich Style) | Key Contents | Origin Session (Full ID) | Local Backup |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
        f"| **🧭 Hub** | `{now_str[:16]}` | [**`PROJECT_HUB.md`**](file:///{brain_norm}/PROJECT_HUB.md) | Master hub with Fork Tree, context telemetry, and activity logs. | `{primary_brain_dir.name}` | [`INDEX.md`](./INDEX.md) |",
    ]
    for doc in sorted_docs:
        md_name = doc["name"]
        st = doc["stats"]
        lines.append(
            f"| **{doc['category']}** | `{doc['updated_str']}` | [**`{md_name}`**](file:///{brain_norm}/{md_name}) | {doc['purpose']} | `{doc['origin_sid']}` (`{st['line_count']} lines`) | [`notes/{md_name}`](./notes/{md_name}) |"
        )

    lines.extend(
        [
            "",
            "## 2. Sessions & Fork Telemetry",
            "",
            "| Role & Fork Lineage | Full Session ID | Context (Active / Peak) | Chats & Steps | Active Window |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for s in sessions:
        lineage = (
            f"🔀 Fork of `{s['parent_id'][:8]}` @ `step {s['fork_step']}`"
            if s["parent_id"]
            else "🌱 Root (`step 0`)"
        )
        cur_ctx = format_tokens(s["current_ctx_tokens"])
        peak_ctx = format_tokens(s["peak_ctx_tokens"])
        step_span = s["last_step"] - s["first_step"] + 1
        lines.append(
            f"| {lineage} | `{s['id']}` | `{cur_ctx}` / `{peak_ctx}` | `{s['user_chats']} chats` (`{step_span} steps`, `#{s['first_step']}..#{s['last_step']}`) | `{s['started_local']}` -> `{s['last_active']}` |"
        )

    lines.extend(
        [
            "",
            "## 3. Browser HTML Dashboards (`.local-notes/`)",
            "",
            "- [**Master Interactive HTML Hub (`index.html`)**](./index.html)",
        ]
    )
    for v in viz_files:
        lines.append(f"- [**{v.stem.replace('_', ' ').title()} (`viz/{v.name}`)**](./viz/{v.name})")

    index_path = local_notes_dir / "INDEX.md"
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return index_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bidirectional sync of multi-session artifacts & fork telemetry into native Antigravity brain folders & .local-notes/"
    )
    parser.add_argument("--workspace", type=str, default=".", help="Workspace directory path")
    parser.add_argument(
        "--brain-dir",
        type=str,
        default=str(Path.home() / ".gemini" / "antigravity-cli" / "brain"),
        help="Path to Antigravity brain directory",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default="",
        help="Optional current conversation ID; syncs into all matched sessions for this workspace.",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    brain_dir = Path(args.brain_dir).resolve()

    local_notes_dir = workspace / ".local-notes"
    notes_dir = local_notes_dir / "notes"
    viz_dir = local_notes_dir / "viz"
    assets_dir = local_notes_dir / "assets"

    for d in (local_notes_dir, notes_dir, viz_dir, assets_dir):
        d.mkdir(parents=True, exist_ok=True)

    ensure_git_exclude(workspace, ".local-notes/")
    git_state = collect_git_state(workspace)
    sessions, origin_map, authored_ts_map = scan_brain_sessions(brain_dir, workspace)

    target_sids = [s["id"] for s in sessions]
    if args.session_id and args.session_id not in target_sids:
        target_sids.insert(0, args.session_id)

    canonical_images, canonical_mds = collect_canonical_artifacts(
        sessions, origin_map, authored_ts_map, notes_dir, assets_dir, workspace
    )
    sorted_docs = sorted(
        canonical_mds.values(),
        key=lambda d: (d["priority"], d["updated_str"] == "", d["name"]),
    )
    sorted_docs.sort(key=lambda d: d["updated_str"], reverse=True)
    sorted_docs.sort(key=lambda d: d["priority"])

    hubs = sync_all_targets(
        sessions,
        canonical_images,
        canonical_mds,
        workspace,
        git_state,
        target_sids,
        brain_dir,
        notes_dir,
        assets_dir,
    )

    if target_sids:
        primary_brain = brain_dir / (args.session_id or target_sids[0])
        update_local_index_md_with_native_links(
            local_notes_dir, workspace, git_state, sorted_docs, viz_dir, primary_brain, sessions
        )

    print(
        f"Synced {len(sorted_docs)} artifacts across {len(sessions)} sessions/forks ({len(hubs)} native brain hubs)."
    )
    for h in hubs:
        print(f"Native Hub: {h}")


if __name__ == "__main__":
    main()
