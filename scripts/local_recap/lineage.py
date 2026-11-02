"""SQLite metadata decoding, workspace URI normalization, and Multi-Root Fork & Subagent Forest reconstruction."""

from __future__ import annotations

import json
import re
import sqlite3
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


def normalize_workspace_variants(raw_uri_or_path: str | Path) -> set[str]:
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


def parse_workspace_uris(raw_ws_uris: str) -> set[str]:
    """Extract normalized workspace path variants from `conversation_summaries.workspace_uris`."""
    if not raw_ws_uris or not raw_ws_uris.strip():
        return set()
    paths: set[str] = set()
    try:
        parsed = json.loads(raw_ws_uris)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, str):
                    paths.update(normalize_workspace_variants(item))
        elif isinstance(parsed, str):
            paths.update(normalize_workspace_variants(parsed))
    except Exception:
        for m in re.findall(r'file://[^\s"\'\],]+', raw_ws_uris):
            paths.update(normalize_workspace_variants(m))
    return paths


def query_antigravity_sqlite_metadata(
    ag_dir: Path, workspace: Path
) -> dict[str, dict[str, Any]]:
    """Read ground-truth workspace matching, titles, and exact fork lineage from Antigravity's
    SQLite databases (`conversation_summaries.db` and `conversations/<id>.db`), `history.jsonl`,
    and `annotations/<id>.pbtxt`.
    """
    meta: dict[str, dict[str, Any]] = {}
    ws_variants = normalize_workspace_variants(workspace)

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
                        normalize_workspace_variants(h_ws)
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
                db_paths = parse_workspace_uris(ws_uris or "")
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


def reconstruct_fork_forest(sessions: list[dict[str, Any]]) -> None:
    """Mutate `sessions` in-place to populate `parent_id`, `root_id`, `fork_depth`,
    `fork_step`, `lineage_source`, and `tree_num`.
    """
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
                    int(st_idx)
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
