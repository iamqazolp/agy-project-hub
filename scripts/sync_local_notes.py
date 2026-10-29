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
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.parse
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


def _normalize_workspace_variants(raw_uri_or_path: str | Path) -> set[str]:
    """Normalize a filesystem path or `file://` URI into lowercase forward-slash path variants
    (including both symlink path and resolved target path when present on disk).
    """
    text = urllib.parse.unquote(str(raw_uri_or_path or "").strip()).strip("\"'")
    if not text:
        return set()
    if text.lower().startswith("file://"):
        text = text[7:]
        if re.match(r"^/[a-zA-Z]:/", text):
            text = text[1:]
    norm = text.replace("\\", "/").rstrip("/").lower()
    if not norm:
        return set()
    variants = {norm}
    try:
        p = Path(text)
        if p.exists():
            variants.add(str(p.resolve()).replace("\\", "/").rstrip("/").lower())
    except Exception:
        pass
    return variants


def _parse_workspace_uris(raw_ws_uris: str) -> set[str]:
    """Extract normalized workspace path variants from `conversation_summaries.workspace_uris`."""
    if not raw_ws_uris or not raw_ws_uris.strip():
        return set()
    paths: set[str] = set()
    try:
        parsed = json.loads(raw_ws_uris)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, str):
                    paths.update(_normalize_workspace_variants(item))
        elif isinstance(parsed, str):
            paths.update(_normalize_workspace_variants(parsed))
    except Exception:
        for m in re.findall(r'file://[^\s"\'\],]+', raw_ws_uris):
            paths.update(_normalize_workspace_variants(m))
    return paths


def query_antigravity_sqlite_metadata(
    ag_dir: Path, workspace: Path
) -> dict[str, dict[str, Any]]:
    """Read ground-truth workspace matching, titles, and exact fork lineage from Antigravity's
    SQLite databases (`conversation_summaries.db` and `conversations/<id>.db`), `history.jsonl`,
    and `annotations/<id>.pbtxt`.
    """
    meta: dict[str, dict[str, Any]] = {}
    ws_variants = _normalize_workspace_variants(workspace)

    history_workspaces: dict[str, set[str]] = {}
    history_file = ag_dir / "history.jsonl"
    if history_file.exists():
        try:
            for line in history_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    hobj = json.loads(line)
                except Exception:
                    continue
                if hobj.get("type") == "slash_command":
                    continue
                h_cid = str(hobj.get("conversationId") or "").strip()
                h_ws = str(hobj.get("workspace") or "").strip()
                if h_cid and h_ws:
                    history_workspaces.setdefault(h_cid, set()).update(
                        _normalize_workspace_variants(h_ws)
                    )
        except Exception:
            pass

    summaries_db = ag_dir / "conversation_summaries.db"
    if summaries_db.exists():
        try:
            conn = sqlite3.connect(f"file:{summaries_db}?mode=ro", uri=True)
            rows = conn.execute(
                "SELECT conversation_id, title, step_count, workspace_uris, parent_conversation_id, "
                "agent_name, nesting_depth FROM conversation_summaries"
            ).fetchall()
            for cid, title, step_count, ws_uris, parent_cid, agent_name, nesting_depth in rows:
                db_paths = _parse_workspace_uris(ws_uris or "")
                cid_paths = db_paths if db_paths else history_workspaces.get(cid, set())
                matched_ws = bool(cid_paths & ws_variants)
                known_other = bool(cid_paths) and not matched_ws
                clean_title = (title or "").strip()
                if not clean_title:
                    ann_file = ag_dir / "annotations" / f"{cid}.pbtxt"
                    if ann_file.exists():
                        m_title = re.search(
                            r'title:\s*"([^"]+)"',
                            ann_file.read_text(encoding="utf-8", errors="ignore"),
                        )
                        if m_title:
                            clean_title = m_title.group(1).strip()
                meta[cid] = {
                    "matched_workspace": matched_ws,
                    "known_other_workspace": known_other,
                    "title": clean_title,
                    "db_step_count": int(step_count or 0),
                    "subagent_parent_id": (parent_cid or "").strip(),
                    "agent_name": (agent_name or "").strip(),
                    "nesting_depth": int(nesting_depth or 0),
                    "ancestry": [],
                }
            conn.close()
        except Exception:
            pass

    for h_cid, h_paths in history_workspaces.items():
        if h_cid not in meta:
            matched_ws = bool(h_paths & ws_variants)
            meta[h_cid] = {
                "matched_workspace": matched_ws,
                "known_other_workspace": bool(h_paths) and not matched_ws,
                "title": "",
                "db_step_count": 0,
                "subagent_parent_id": "",
                "agent_name": "",
                "nesting_depth": 0,
                "ancestry": [],
            }

    # Propagate workspace membership to subagents whose parent session belongs to this workspace
    for _ in range(3):
        for info in meta.values():
            spid = info.get("subagent_parent_id") or ""
            if spid and spid in meta:
                if meta[spid]["matched_workspace"]:
                    info["matched_workspace"] = True
                    info["known_other_workspace"] = False
                elif meta[spid]["known_other_workspace"]:
                    info["matched_workspace"] = False
                    info["known_other_workspace"] = True

    conv_dir = ag_dir / "conversations"
    if conv_dir.exists():
        for db_file in conv_dir.glob("*.db"):
            cid = db_file.stem
            if cid not in meta or not meta[cid].get("matched_workspace"):
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
    brain_dir: Path | str, workspace: Path | str
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    """Scan all `brain/*` directories for sessions matching `workspace`, extract full telemetry
    (context tokens, chat counts, step indices, timestamps), and reconstruct the Multi-Root Fork Forest.
    """
    brain_dir = Path(brain_dir)
    workspace = Path(workspace)
    if not brain_dir.exists():
        return [], {}, {}
    ws_name = workspace.name.lower()
    ws_variants = _normalize_workspace_variants(workspace)
    sqlite_meta = query_antigravity_sqlite_metadata(brain_dir.parent, workspace)
    has_sqlite_db = (brain_dir.parent / "conversation_summaries.db").exists()
    ws_path_patterns = [
        re.compile(rf"(?<![a-z0-9_/-]){re.escape(v)}(?![a-z0-9_.-])")
        for v in ws_variants
    ]
    ws_seg_pattern = re.compile(rf"/{re.escape(ws_name)}(?:/|[\"\'\s]|$)")
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
        last_known_end_tokens = 0
        raw_head_snippet = ""

        if transcript.exists():
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

    # Reconstruct Multi-Root Fork & Subagent Forest (`parent_id`, `root_id`, `fork_depth`, `fork_step`)
    sess_by_id = {s["id"]: s for s in sessions}
    all_ids = list(sess_by_id.keys())
    for s in sessions:
        spid = s.get("subagent_parent_id") or ""
        if spid:
            s["parent_id"] = spid
            s["is_subagent"] = True
            s["fork_depth"] = max(1, int(s.get("nesting_depth") or 1))
            s["lineage_source"] = "sqlite_subagent_parent"
            parent_obj = sess_by_id.get(spid)
            if parent_obj and s["first_ts_iso"]:
                prior_steps = [
                    st_idx
                    for st_idx, st_ts in parent_obj["step_timestamps"].items()
                    if st_ts <= s["first_ts_iso"]
                ]
                if prior_steps:
                    s["fork_step"] = max(prior_steps)
            continue

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
            max_allowed_diff = max(16000, int(child_open_ctx * 0.35)) if child_open_ctx > 0 else 999999999
            for cand in sessions:
                if cand["id"] == s["id"] or cand.get("is_subagent"):
                    continue
                if cand["first_step"] <= fork_point <= cand["last_step"]:
                    step_ts = cand["step_timestamps"].get(fork_point, cand["first_ts_iso"])
                    if step_ts <= s["first_ts_iso"]:
                        parent_end_tok = cand["step_end_tokens"].get(fork_point, 0)
                        if child_open_ctx > 0 and parent_end_tok > 0:
                            tok_diff = abs(child_open_ctx - parent_end_tok)
                            if tok_diff > max_allowed_diff:
                                continue
                        else:
                            tok_diff = 999999999
                        scored_candidates.append((tok_diff, -cand["first_step"], step_ts, cand["id"]))
            if scored_candidates:
                scored_candidates.sort(key=lambda x: (x[0], x[1]))
                best_parent = scored_candidates[0][3]
                s["lineage_source"] = "token_timestamp_fingerprint"

        s["parent_id"] = best_parent

    # Resolve `root_id` and `fork_depth` for any fallback-matched or subagent sessions & assign Root Tree numbers
    for s in sessions:
        if s["parent_id"]:
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
            if s["fork_depth"] == 0:
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


def write_artifact_metadata(
    md_file: Path,
    summary: str,
    origin_sid: str = "",
    updated_at_iso: str = "",
) -> None:
    """Write companion `<name>.md.metadata.json` so Antigravity renders `md_file` natively."""
    meta_path = md_file.parent / f"{md_file.name}.metadata.json"
    ts_iso = updated_at_iso or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f0Z")
    payload: dict[str, Any] = {
        "summary": summary,
        "updatedAt": ts_iso,
        "userFacing": True,
    }
    if origin_sid:
        payload["originSession"] = origin_sid
    new_json = json.dumps(payload, indent=2)
    if meta_path.exists():
        try:
            if meta_path.read_text(encoding="utf-8", errors="ignore").strip() == new_json.strip():
                return
        except Exception:
            pass
    meta_path.write_text(new_json, encoding="utf-8", newline="\n")


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

        # Skip previously-synced duplicate copies in non-origin brain folders when the original brain file exists
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


def _write_text_preserving_mtime(dst: Path, content: str, mtime: float | None = None) -> None:
    """Write `content` to `dst` only if changed or missing, and preserve `mtime` when provided."""
    changed = True
    if dst.exists():
        try:
            if dst.read_text(encoding="utf-8", errors="ignore") == content:
                changed = False
        except Exception:
            pass
    if changed:
        dst.write_text(content, encoding="utf-8", newline="\n")
    if mtime is not None:
        try:
            os.utime(dst, (mtime, mtime))
        except Exception:
            pass


def _create_file_shortcut(src_brain_file: Path, dst_shortcut: Path) -> None:
    """Create a symlink shortcut at `dst_shortcut` pointing directly to `src_brain_file`."""
    src_resolved = src_brain_file.resolve()
    if dst_shortcut.is_symlink() or dst_shortcut.exists():
        try:
            if dst_shortcut.is_symlink() and dst_shortcut.resolve() == src_resolved:
                return
        except Exception:
            pass
        dst_shortcut.unlink(missing_ok=True)
    try:
        os.symlink(src_resolved, dst_shortcut)
    except OSError:
        try:
            os.link(src_resolved, dst_shortcut)
        except OSError:
            norm_target = str(src_resolved).replace("\\", "/").lstrip("/")
            dst_shortcut.write_text(
                f"# Shortcut -> [{src_resolved.name}](file:///{norm_target})\n",
                encoding="utf-8",
                newline="\n",
            )


def sync_local_shortcuts(
    local_notes_dir: Path,
    primary_brain_dir: Path,
    sorted_docs: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
) -> None:
    """Populate `<workspace>/.local-notes/` exclusively with shortcuts pointing to the
    original files in `brain/` (including `PROJECT_HUB.md`), and remove legacy physical copies.
    """
    local_notes_dir.mkdir(parents=True, exist_ok=True)

    # Clean up legacy physical subdirectories (`notes/`, `assets/`, `viz/`) and legacy index files
    for legacy_sub in ("notes", "assets"):
        sub_path = local_notes_dir / legacy_sub
        if sub_path.is_symlink():
            sub_path.unlink(missing_ok=True)
        elif sub_path.is_dir():
            shutil.rmtree(sub_path, ignore_errors=True)

    viz_sub = local_notes_dir / "viz"
    if viz_sub.is_dir() and not viz_sub.is_symlink():
        for html_f in viz_sub.glob("*.html"):
            if not html_f.is_symlink() and primary_brain_dir.exists():
                dst_brain_html = primary_brain_dir / html_f.name
                if not dst_brain_html.exists():
                    shutil.copy2(html_f, dst_brain_html)
        shutil.rmtree(viz_sub, ignore_errors=True)

    for legacy_file in ("INDEX.md", "index.html"):
        lf = local_notes_dir / legacy_file
        if lf.exists() or lf.is_symlink():
            lf.unlink(missing_ok=True)

    expected_names: set[str] = set()

    # 1. Shortcut for `PROJECT_HUB.md` -> `<primary_brain_dir>/PROJECT_HUB.md`
    primary_hub = primary_brain_dir / "PROJECT_HUB.md"
    if primary_hub.exists():
        _create_file_shortcut(primary_hub, local_notes_dir / "PROJECT_HUB.md")
        expected_names.add("PROJECT_HUB.md")

    # 2. Shortcuts for every canonical Markdown artifact -> `<brain_dir>/<origin_sid>/<doc.name>`
    for doc in sorted_docs:
        orig_brain_path = Path(doc.get("brain_path") or (primary_brain_dir.parent / doc["origin_sid"] / doc["name"]))
        if orig_brain_path.exists():
            _create_file_shortcut(orig_brain_path, local_notes_dir / doc["name"])
            expected_names.add(doc["name"])

    # 3. Shortcuts for any HTML visualizations in brain sessions -> `<brain_dir>/<sid>/<viz.html>`
    for sess in sessions:
        for art in sess["artifacts"]:
            if not art.is_symlink() and art.suffix.lower() == ".html" and art.exists():
                _create_file_shortcut(art, local_notes_dir / art.name)
                expected_names.add(art.name)

    # Remove stale symlinks or leftover physical `.md` copies in `.local-notes/`
    for item in local_notes_dir.iterdir():
        if item.name not in expected_names:
            if item.is_symlink() or (item.is_file() and item.suffix.lower() in {".md", ".html"}):
                item.unlink(missing_ok=True)


def ensure_vscode_editor_associations(workspace: Path | None = None) -> None:
    """Ensure VS Code's `workbench.editorAssociations` maps `.local-notes/*.md` shortcuts
    to `antigravity.artifactEditor` so clicking them in the VS Code Explorer opens the
    Antigravity Artifact Viewer style instead of raw Markdown text.
    """
    home = Path.home()
    candidates: list[Path] = []
    if sys.platform == "darwin":
        app_support = home / "Library" / "Application Support"
        candidates = [
            app_support / "Code" / "User" / "settings.json",
            app_support / "Antigravity" / "User" / "settings.json",
            app_support / "Cursor" / "User" / "settings.json",
        ]
    elif os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        candidates = [
            appdata / "Code" / "User" / "settings.json",
            appdata / "Antigravity" / "User" / "settings.json",
            appdata / "Cursor" / "User" / "settings.json",
        ]
    else:
        cfg = home / ".config"
        candidates = [
            cfg / "Code" / "User" / "settings.json",
            cfg / "Antigravity" / "User" / "settings.json",
            cfg / "Cursor" / "User" / "settings.json",
        ]
    if workspace and (workspace / ".vscode" / "settings.json").exists():
        candidates.append(workspace / ".vscode" / "settings.json")

    for settings_path in candidates:
        if not settings_path.parent.exists():
            continue
        data: dict[str, Any] = {}
        if settings_path.exists():
            try:
                loaded = json.loads(settings_path.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                continue
        assoc = data.get("workbench.editorAssociations")
        if not isinstance(assoc, dict):
            assoc = {}
        changed = False
        for pattern in ("**/.local-notes/*.md", "**/.local-notes/**/*.md", "**/.gemini/*/brain/**/*.md"):
            if assoc.get(pattern) != "antigravity.artifactEditor":
                assoc[pattern] = "antigravity.artifactEditor"
                changed = True
        if changed:
            data["workbench.editorAssociations"] = assoc
            try:
                settings_path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8", newline="\n")
            except Exception:
                pass


def bridge_ide_and_cli_brain_sessions(brain_dir: Path, session_ids: list[str]) -> Path:
    """Bridge session folders between `~/.gemini/antigravity-cli/brain` (CLI) and
    `~/.gemini/antigravity/brain` (VS Code extension `--app_data_dir=antigravity`) so
    links in `PROJECT_HUB.md` open natively in both environments.
    """
    ide_brain = Path.home() / ".gemini" / "antigravity" / "brain"
    cli_brain = Path.home() / ".gemini" / "antigravity-cli" / "brain"
    try:
        if brain_dir.resolve() == cli_brain.resolve() and ide_brain.parent.exists():
            ide_brain.mkdir(parents=True, exist_ok=True)
            for sid in session_ids:
                if not sid:
                    continue
                src = cli_brain / sid
                dst = ide_brain / sid
                if src.exists() and not dst.exists() and not dst.is_symlink():
                    try:
                        os.symlink(src.resolve(), dst)
                    except OSError:
                        pass
            return ide_brain
    except Exception:
        pass
    return brain_dir


def sync_all_targets(
    sessions: list[dict[str, Any]],
    canonical_images: dict[str, Path],
    canonical_mds: dict[str, dict[str, Any]],
    workspace: Path,
    git_state: dict[str, Any],
    target_session_ids: list[str],
    brain_dir: Path,
) -> list[Path]:
    """Ensure canonical artifacts exist in their origin `brain/<id>/` folder and generate `PROJECT_HUB.md`."""
    sorted_docs = sort_canonical_docs(canonical_mds)
    all_sids = list({s["id"] for s in sessions} | set(target_session_ids) | {d["origin_sid"] for d in sorted_docs})
    link_brain_dir = bridge_ide_and_cli_brain_sessions(brain_dir, all_sids)

    for doc in sorted_docs:
        raw_txt = doc["path"].read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
        # Ensure the canonical original file exists in its origin session's `brain/<origin_sid>/` folder
        orig_sid = doc["origin_sid"]
        orig_bdir = brain_dir / orig_sid
        if orig_bdir.exists():
            for img_name, src_img in canonical_images.items():
                dst_img = orig_bdir / img_name
                if src_img.resolve() != dst_img.resolve():
                    shutil.copy2(src_img, dst_img)
            orig_md = orig_bdir / doc["name"]
            rewritten_orig = rewrite_md_images_for_brain_dir(raw_txt, orig_bdir)
            _write_text_preserving_mtime(orig_md, rewritten_orig, doc["mtime"])
            doc_iso = dt.datetime.fromtimestamp(doc["mtime"], tz=dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f0Z"
            )
            write_artifact_metadata(orig_md, doc["purpose"], orig_sid, updated_at_iso=doc_iso)
            doc["brain_path"] = orig_md

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

        # Remove stale duplicate copies of other sessions' artifacts that were synced into `tdir` previously
        for doc in sorted_docs:
            if doc["origin_sid"] != sid and doc.get("brain_path") and Path(doc["brain_path"]).exists():
                stale_md = tdir / doc["name"]
                stale_meta = tdir / f"{doc['name']}.metadata.json"
                if stale_md.exists() and stale_meta.exists():
                    try:
                        mobj = json.loads(stale_meta.read_text(encoding="utf-8", errors="ignore"))
                        if mobj.get("originSession") == doc["origin_sid"]:
                            stale_md.unlink(missing_ok=True)
                            stale_meta.unlink(missing_ok=True)
                    except Exception:
                        pass

        hub_lines = [
            f"# ⚡ `{workspace.name}` — Multi-Session & Fork Command Center",
            "",
            "> [!TIP]",
            f"> **Zero-Context-Overhead Sync:** All {len(sorted_docs)} project guides and {len(sessions)} session/fork logs are indexed in this session's native artifact hub (`{sid}`) by an external Python script (`0` LLM tokens used). Click any document below to open the original brain artifact in **Antigravity's native styled Artifact Viewer**.",
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
            bridged_candidate = link_brain_dir / orig_full / md_name
            orig_brain_path = (
                bridged_candidate
                if bridged_candidate.exists()
                else (doc.get("brain_path") or (brain_dir / orig_full / md_name))
            )
            orig_brain_norm = str(orig_brain_path).replace("\\", "/").lstrip("/")
            doc_col = f"[**`{md_name}`**](file:///{orig_brain_norm})"
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
            if s.get("is_subagent"):
                agent_lbl = s.get("agent_name") or "subagent"
                at_step = f" @ `step {s['fork_step']}`" if s.get("fork_step") is not None else ""
                lineage = (
                    f"`Tree #{t_num}` · 🤖 **Subagent (`{agent_lbl}`, d={f_depth})** of "
                    f"`{s['parent_id'][:8]}`{at_step}{title_tag}{is_cur}"
                )
            elif s["parent_id"]:
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
            doc_links: list[str] = []
            for a in valid_authored:
                orig_sid_a = canonical_mds[a]["origin_sid"]
                bridged_art = link_brain_dir / orig_sid_a / a
                s_art_path = s["path"] / a
                if bridged_art.exists():
                    target_art = bridged_art
                elif s_art_path.exists():
                    target_art = s_art_path
                else:
                    target_art = canonical_mds[a].get("brain_path") or (brain_dir / orig_sid_a / a)
                target_norm = str(target_art).replace("\\", "/").lstrip("/")
                doc_links.append(f"[`{a}`](file:///{target_norm})")
            docs_cell = " · ".join(doc_links) if doc_links else "—"
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
                if s.get("is_subagent"):
                    agent_lbl = s.get("agent_name") or "subagent"
                    role_lbl = f"Subagent {agent_lbl}"
                elif s["parent_id"]:
                    role_lbl = f"Fork d={f_depth} @{s['fork_step']}"
                else:
                    role_lbl = "Root"
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
                    if s.get("is_subagent"):
                        agent_lbl = s.get("agent_name") or "subagent"
                        edge_lbl = f"subagent ({agent_lbl})" + (f" @ step {fk_step}" if fk_step is not None else "")
                    else:
                        edge_lbl = f"forked @ step {fk_step}"
                    hub_lines.append(f'        N{pnum} -- "{edge_lbl}" --> N{num}')
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
            if s.get("is_subagent"):
                agent_lbl = s.get("agent_name") or "subagent"
                role_badge = f"Subagent (`{agent_lbl}`) of `{s['parent_id']}`" + (
                    f" @ step `{s['fork_step']}`" if s.get("fork_step") is not None else ""
                )
            elif s["parent_id"]:
                role_badge = f"Fork of `{s['parent_id']}` @ step `{s['fork_step']}`"
            else:
                role_badge = "Root Session (`step 0`)"
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


def resolve_default_brain_dir(session_id: str = "") -> Path:
    """Auto-resolve the active Antigravity brain directory across CLI and IDE data paths."""
    candidates = [
        Path.home() / ".gemini" / "antigravity-cli" / "brain",
        Path.home() / ".gemini" / "antigravity" / "brain",
    ]
    if session_id:
        for cand in candidates:
            if (cand / session_id).exists():
                return cand
    for cand in candidates:
        if cand.exists():
            return cand
    return candidates[0]


def run_sync(
    workspace: Path,
    brain_dir: Path,
    session_id: str = "",
    quiet: bool = False,
) -> list[Path]:
    """Synchronize `PROJECT_HUB.md` across all project brain sessions and update `<workspace>/.local-notes/` shortcuts."""
    local_notes_dir = workspace / ".local-notes"
    local_notes_dir.mkdir(parents=True, exist_ok=True)

    ensure_git_exclude(workspace, ".local-notes/")
    ensure_vscode_editor_associations(workspace)
    git_state = collect_git_state(workspace)
    sessions, origin_map, authored_ts_map = scan_brain_sessions(brain_dir, workspace)

    target_sids = [s["id"] for s in sessions if not s.get("is_subagent")]
    if not target_sids:
        target_sids = [s["id"] for s in sessions]
    if session_id and session_id not in target_sids:
        target_sids.insert(0, session_id)

    canonical_images, canonical_mds = collect_canonical_artifacts(
        sessions, origin_map, authored_ts_map, local_notes_dir, workspace
    )
    sorted_docs = sort_canonical_docs(canonical_mds)

    hubs = sync_all_targets(
        sessions,
        canonical_images,
        canonical_mds,
        workspace,
        git_state,
        target_sids,
        brain_dir,
    )

    if target_sids:
        primary_brain = brain_dir / (session_id or target_sids[0])
        sync_local_shortcuts(local_notes_dir, primary_brain, sorted_docs, sessions)

    if not quiet:
        print(
            f"Synced {len(sorted_docs)} artifacts across {len(sessions)} sessions/forks ({len(hubs)} native brain hubs)."
        )
        for h in hubs:
            print(f"Native Hub: {h}")
    return hubs


def run_from_hook(hook_event: str) -> None:
    """Handle Antigravity `PostInvocation`, `PostToolUse`, and `Stop` lifecycle hooks to keep
    `PROJECT_HUB.md` and `.local-notes/` shortcuts continuously updated with 0 LLM context cost.
    """
    try:
        raw_stdin = sys.stdin.read().strip()
        payload = json.loads(raw_stdin) if raw_stdin else {}
        conv_id = str(payload.get("conversationId") or "").strip()
        ws_paths = payload.get("workspacePaths") or []
        art_dir = str(payload.get("artifactDirectoryPath") or "").strip()

        workspace: Path | None = None
        for wp in ws_paths:
            cand = Path(str(wp)).expanduser()
            if cand.exists() and cand.is_dir():
                workspace = cand.resolve()
                break
        if workspace is None:
            workspace = Path.cwd().resolve()

        if art_dir and Path(art_dir).exists():
            brain_dir = Path(art_dir).resolve().parent
        else:
            brain_dir = resolve_default_brain_dir(conv_id).resolve()

        has_hub_or_local_notes = (
            (workspace / ".local-notes").exists()
            or (workspace / ".git").exists()
            or bool(conv_id and (brain_dir / conv_id / "PROJECT_HUB.md").exists())
        )

        should_sync = False
        if hook_event == "post_tool":
            tool_call = payload.get("toolCall") or {}
            args_obj = tool_call.get("args") or {}
            target_path = (
                str(args_obj.get("Path") or args_obj.get("TargetFile") or "")
                .strip('"')
                .replace("\\", "/")
            )
            low_target = target_path.lower()
            if (
                "/brain/" in low_target
                and low_target.endswith((".md", ".html"))
                and not low_target.endswith("/project_hub.md")
            ):
                should_sync = True
        elif hook_event in {"post_invocation", "stop"}:
            if has_hub_or_local_notes:
                should_sync = True

        if should_sync:
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--workspace",
                str(workspace),
                "--brain-dir",
                str(brain_dir),
                "--quiet",
            ]
            if conv_id:
                cmd.extend(["--session-id", conv_id])
            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except Exception:
        pass

    if hook_event == "stop":
        sys.stdout.write(json.dumps({"decision": "allow"}) + "\n")
    else:
        sys.stdout.write("{}\n")
    sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync multi-session artifacts & fork telemetry into native Antigravity brain hubs and .local-notes/ shortcuts"
    )
    parser.add_argument("--workspace", type=str, default=".", help="Workspace directory path")
    parser.add_argument(
        "--brain-dir",
        type=str,
        default="",
        help="Path to Antigravity brain directory (auto-detected if omitted)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default="",
        help="Optional current conversation ID; syncs into all matched sessions for this workspace.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout progress output (used by background hook sync)",
    )
    parser.add_argument(
        "--from-hook",
        type=str,
        choices=["post_invocation", "post_tool", "stop"],
        default="",
        help="Internal lifecycle hook mode ('post_invocation', 'post_tool', or 'stop')",
    )
    args = parser.parse_args()

    if args.from_hook:
        run_from_hook(args.from_hook)
        return

    workspace = Path(args.workspace).resolve()
    brain_dir = (
        Path(args.brain_dir).expanduser().resolve()
        if args.brain_dir
        else resolve_default_brain_dir(args.session_id).resolve()
    )
    run_sync(workspace, brain_dir, session_id=args.session_id, quiet=args.quiet)


if __name__ == "__main__":
    main()
