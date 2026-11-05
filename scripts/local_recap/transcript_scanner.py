"""Session transcript scanner and Multi-Root Fork & Subagent Forest reconstructor."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .models import PromptEntry, SessionInfo, SqliteSessionMeta, TouchEvent, utc_iso_to_local_str
from .sqlite_metadata import _normalize_workspace_variants, query_antigravity_sqlite_metadata


def extract_user_request_text(content: str) -> str:
    """Extract the raw user request text from `<USER_REQUEST>` tags or plain prompt text."""
    m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, flags=re.DOTALL)
    return m.group(1).strip() if m else content.strip()


def scan_brain_sessions(
    brain_dir: Path | str, workspace: Path | str
) -> tuple[list[SessionInfo], dict[str, str], dict[str, str]]:
    """Scan all `brain/*` directories for sessions matching `workspace`, extract full telemetry
    (context tokens, chat counts, step indices, timestamps, touched files), and reconstruct the
    Multi-Root Fork & Subagent Forest.
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
    ws_norm_prefix = str(workspace.resolve()).replace("\\", "/").rstrip("/") + "/"

    sessions: list[SessionInfo] = []
    origin_map: dict[str, tuple[str, str]] = {}  # md_name -> (earliest_ts, session_id)
    latest_write_ts: dict[str, str] = {}  # md_name -> latest write_file ISO timestamp
    transcript_subagent_parents: dict[str, str] = {}  # subagent_cid -> parent_cid

    brain_dirs_to_scan = [brain_dir]
    if brain_dir.name == "brain" and brain_dir.parent.name in {"antigravity", "antigravity-cli"}:
        sibling_name = "antigravity" if brain_dir.parent.name == "antigravity-cli" else "antigravity-cli"
        sibling_brain = brain_dir.parent.parent / sibling_name / "brain"
        if sibling_brain.exists() and sibling_brain != brain_dir:
            brain_dirs_to_scan.append(sibling_brain)

    conv_dirs_by_cid: dict[str, Path] = {}
    for bdir in brain_dirs_to_scan:
        for cand_dir in bdir.iterdir():
            if not cand_dir.is_dir():
                continue
            cid = cand_dir.name
            existing = conv_dirs_by_cid.get(cid)
            if existing is None:
                conv_dirs_by_cid[cid] = cand_dir
            else:
                ex_tr = existing / ".system_generated" / "logs" / "transcript.jsonl"
                ca_tr = cand_dir / ".system_generated" / "logs" / "transcript.jsonl"
                if ca_tr.exists() and (not ex_tr.exists() or ca_tr.stat().st_mtime > ex_tr.stat().st_mtime):
                    conv_dirs_by_cid[cid] = cand_dir

    for cid, conv_dir in conv_dirs_by_cid.items():
        db_info = sqlite_meta.get(cid, SqliteSessionMeta())
        if db_info.known_other_workspace:
            continue

        transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
        top_files = [
            p
            for p in conv_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in {".md", ".png", ".svg", ".html", ".pdf"}
            and p.name != "PROJECT_HUB.md"
        ]
        matched = bool(db_info.matched_workspace)
        user_prompts: list[PromptEntry] = []
        authored_docs: set[str] = set()
        touched_files: dict[str, TouchEvent] = {}
        first_ts_iso = ""
        last_ts_iso = ""
        first_step: int | None = None
        last_step: int | None = None
        step_timestamps: dict[int, str] = {}
        step_end_tokens: dict[int, int] = {}
        step_ctx_tokens: dict[int, int] = {}
        chat_steps: list[int] = []
        first_planner_ctx_tokens = 0
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
                    if "Created the following subagent:" in raw_text:
                        for m_sub in re.finditer(
                            r'Created the following subagent:[\s\\n]*\{[\s\\n]*\\?"conversationId\\?"\s*:\s*\\?"([0-9a-f-]{36})\\?"',
                            raw_text,
                        ):
                            transcript_subagent_parents[m_sub.group(1)] = cid
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
                            if isinstance(s_idx, int):
                                step_ctx_tokens[s_idx] = ctx_tok
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
                            if isinstance(s_idx, int):
                                chat_steps.append(s_idx)
                            req = extract_user_request_text(str(obj["content"]))
                            if req and not req.startswith("<CONTEXT_SUMMARY>"):
                                user_prompts.append(
                                    PromptEntry(
                                        step=s_idx if s_idx is not None else -1,
                                        timestamp=utc_iso_to_local_str(created_at, include_seconds=False),
                                        text=req[:220] + ("..." if len(req) > 220 else ""),
                                    )
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
                                if path_str.startswith(ws_norm_prefix):
                                    rel_f = path_str[len(ws_norm_prefix) :]
                                    if not rel_f.startswith((".local-notes/", ".git/", "__pycache__/")):
                                        touched_files[rel_f] = TouchEvent(
                                            rel=rel_f,
                                            abs=path_str.lstrip("/"),
                                            ts_iso=created_at,
                                            ts_local=utc_iso_to_local_str(created_at, include_seconds=False),
                                            session_id=cid,
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
                SessionInfo(
                    id=cid,
                    title=db_info.title or "",
                    path=conv_dir,
                    first_ts_iso=first_ts_iso,
                    last_ts_iso=last_ts_iso,
                    started_local=utc_iso_to_local_str(first_ts_iso, include_seconds=False),
                    last_active=utc_iso_to_local_str(last_ts_iso, include_seconds=False),
                    mtime=mtime,
                    first_step=first_step if first_step is not None else 0,
                    last_step=last_step if last_step is not None else 0,
                    step_timestamps=step_timestamps,
                    step_end_tokens=step_end_tokens,
                    step_ctx_tokens=step_ctx_tokens,
                    chat_steps=chat_steps,
                    first_planner_ctx_tokens=first_planner_ctx_tokens,
                    user_chats=user_chat_count,
                    current_ctx_tokens=current_ctx_tokens,
                    peak_ctx_tokens=peak_ctx_tokens,
                    total_output_tokens=total_output_tokens,
                    compaction_count=compaction_count,
                    prompts=user_prompts[-8:],
                    artifacts=top_files,
                    authored_docs=sorted(authored_docs),
                    touched_files=touched_files,
                    raw_head_snippet=raw_head_snippet,
                    db_ancestry=list(db_info.ancestry),
                    subagent_parent_id=db_info.subagent_parent_id or "",
                    agent_name=db_info.agent_name or "",
                    nesting_depth=int(db_info.nesting_depth or 0),
                    is_subagent=bool(db_info.subagent_parent_id or int(db_info.nesting_depth or 0) > 0),
                    parent_id=None,
                    root_id=cid,
                    fork_depth=0,
                    fork_step=None,
                    lineage_source="root",
                )
            )

    # Reconstruct Multi-Root Fork & Subagent Forest (`parent_id`, `root_id`, `fork_depth`, `fork_step`)
    sess_by_id = {s.id: s for s in sessions}
    all_ids = list(sess_by_id.keys())
    for s in sessions:
        spid = s.subagent_parent_id or transcript_subagent_parents.get(s.id, "")
        if spid:
            s.subagent_parent_id = spid
            s.parent_id = spid
            s.is_subagent = True
            if not s.agent_name:
                s.agent_name = "self"
            s.fork_depth = max(1, int(s.nesting_depth or 1))
            s.lineage_source = "sqlite_subagent_parent"
            parent_obj = sess_by_id.get(spid)
            if parent_obj and s.first_ts_iso:
                prior_steps = [
                    st_idx
                    for st_idx, st_ts in parent_obj.step_timestamps.items()
                    if st_ts <= s.first_ts_iso
                ]
                if prior_steps:
                    s.fork_step = max(prior_steps)
            continue

        ancestry = s.db_ancestry
        fstep = s.first_step

        # Stage 1 (Ground Truth): SQLite `conversations/<id>.db -> parent_references` protobuf chain
        if ancestry:
            immediate = ancestry[-1]
            s.parent_id = immediate.parent_id
            s.fork_step = (
                immediate.fork_step
                if immediate.fork_step is not None
                else (fstep - 1 if fstep and fstep > 0 else 0)
            )
            s.root_id = ancestry[0].parent_id
            s.fork_depth = len(ancestry)
            s.lineage_source = "sqlite_parent_references"
            continue

        if fstep is None or fstep <= 0:
            s.parent_id = None
            s.fork_step = None
            s.root_id = s.id
            s.fork_depth = 0
            s.lineage_source = "root"
            continue

        fork_point = fstep - 1
        s.fork_step = fork_point
        best_parent = None

        # Stage 2 (Fallback): Check if another session ID is explicitly mentioned in the opening context
        for cand_id in all_ids:
            if cand_id != s.id and cand_id in s.raw_head_snippet:
                best_parent = cand_id
                s.lineage_source = "transcript_context_uuid"
                break

        # Stage 3 (Fallback): Match by step-boundary token fingerprint (`ctx + out` at `fork_point`
        # vs child's `first_planner_ctx_tokens`) + chronological timestamp proximity
        if best_parent is None:
            scored_candidates = []
            child_open_ctx = s.first_planner_ctx_tokens
            max_allowed_diff = max(16000, int(child_open_ctx * 0.35)) if child_open_ctx > 0 else 999999999
            for cand in sessions:
                if cand.id == s.id or cand.is_subagent:
                    continue
                if cand.first_step <= fork_point <= cand.last_step:
                    step_ts = cand.step_timestamps.get(fork_point, cand.first_ts_iso)
                    if step_ts <= s.first_ts_iso:
                        parent_end_tok = cand.step_end_tokens.get(fork_point, 0)
                        if child_open_ctx > 0 and parent_end_tok > 0:
                            tok_diff = abs(child_open_ctx - parent_end_tok)
                            if tok_diff > max_allowed_diff:
                                continue
                        else:
                            tok_diff = 999999999
                        scored_candidates.append((tok_diff, -cand.first_step, step_ts, cand.id))
            if scored_candidates:
                scored_candidates.sort(key=lambda x: (x[0], x[1]))
                best_parent = scored_candidates[0][3]
                s.lineage_source = "token_timestamp_fingerprint"

        s.parent_id = best_parent

    # Resolve `root_id` and `fork_depth` for any fallback-matched or subagent sessions & assign Root Tree numbers
    for s in sessions:
        if s.parent_id:
            depth = 0
            cur = s.parent_id
            visited = {s.id}
            while cur and cur not in visited:
                visited.add(cur)
                depth += 1
                parent_obj = sess_by_id.get(cur)
                if parent_obj and parent_obj.parent_id:
                    cur = parent_obj.parent_id
                else:
                    break
            s.root_id = cur or s.id
            if s.fork_depth == 0:
                s.fork_depth = depth

    # Number Root Trees chronologically (`Root Tree #1`, `Root Tree #2`, ...)
    root_sessions = sorted(
        [s for s in sessions if not s.parent_id],
        key=lambda r: r.first_ts_iso,
    )
    root_tree_map = {r.id: idx + 1 for idx, r in enumerate(root_sessions)}
    for s in sessions:
        if s.root_id not in root_tree_map:
            root_tree_map[s.root_id] = len(root_tree_map) + 1
        s.tree_num = root_tree_map[s.root_id]

    # Propagate inherited trajectory state (title, peak_ctx_tokens, compaction_count,
    # current_ctx_tokens fallback, and inherited_chats) down fork chains in topological order.
    for s in sorted(
        [x for x in sessions if not x.is_subagent and x.parent_id],
        key=lambda x: (x.fork_depth, x.first_step),
    ):
        parent_obj = sess_by_id.get(s.parent_id or "")
        if not parent_obj:
            continue
        fstep = s.fork_step if s.fork_step is not None else max(0, s.first_step - 1)

        if not s.title and parent_obj.title:
            s.title = parent_obj.title

        inherited_ctx_map = {
            st: tok for st, tok in parent_obj.step_ctx_tokens.items() if st <= fstep
        }
        combined_ctx_map = {**inherited_ctx_map, **s.step_ctx_tokens}
        s.step_ctx_tokens = combined_ctx_map

        prev_c = 0
        stitched_compacts = 0
        pre_fork_compacts = 0
        stitched_peak = parent_obj.peak_ctx_tokens if not inherited_ctx_map else 0
        last_c = 0
        for st_idx in sorted(combined_ctx_map.keys()):
            c_tok = combined_ctx_map[st_idx]
            if c_tok <= 0:
                continue
            if prev_c > 60000 and c_tok < prev_c * 0.5:
                stitched_compacts += 1
                if st_idx <= fstep:
                    pre_fork_compacts += 1
            prev_c = c_tok
            last_c = c_tok
            if c_tok > stitched_peak:
                stitched_peak = c_tok

        s.peak_ctx_tokens = max(s.peak_ctx_tokens, stitched_peak)
        s.compaction_count = max(s.compaction_count, stitched_compacts)
        s.inherited_compactions = pre_fork_compacts
        if s.current_ctx_tokens == 0 and last_c > 0:
            s.current_ctx_tokens = last_c

        inherited_chat_list = [st for st in parent_obj.chat_steps if st <= fstep]
        s.inherited_chats = len(inherited_chat_list)
        s.chat_steps = sorted(set(inherited_chat_list) | set(s.chat_steps))

        if not s.prompts and parent_obj.prompts:
            s.prompts = [pr for pr in parent_obj.prompts if pr.step <= fstep][-5:]

    sessions.sort(key=lambda s: s.last_ts_iso, reverse=True)
    clean_origin = {k: v[1] for k, v in origin_map.items()}
    clean_ts = {k: utc_iso_to_local_str(v, include_seconds=False) for k, v in latest_write_ts.items()}
    return sessions, clean_origin, clean_ts
