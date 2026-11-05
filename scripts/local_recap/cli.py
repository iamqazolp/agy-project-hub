"""CLI entrypoint, workspace sync orchestration, and Antigravity lifecycle hook runner for `local-recap`."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .artifact_sync import (
    collect_canonical_artifacts,
    collect_hot_files,
    collect_rich_media,
    ensure_vscode_editor_associations,
    sort_canonical_docs,
    sync_local_shortcuts,
)
from .git_telemetry import collect_git_state, ensure_git_exclude
from .hub_renderer import sync_all_targets
from .models import ArtifactDoc, GitState, SessionInfo, format_size, format_tokens
from .transcript_scanner import scan_brain_sessions


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


def build_telemetry_payload(
    workspace: Path,
    brain_dir: Path,
    session_id: str = "",
    sync_hubs: bool = True,
) -> dict[str, Any]:
    """Run workspace telemetry scan (and optional hub sync) and return a structured JSON-serializable payload
    for the `agy-project-hub` VS Code extension dashboard, sidebar, and status bar.
    """
    local_notes_dir = workspace / ".local-notes"
    local_notes_dir.mkdir(parents=True, exist_ok=True)

    ensure_git_exclude(workspace, ".local-notes/")
    ensure_vscode_editor_associations(workspace)
    git_state = collect_git_state(workspace)
    sessions, origin_map, authored_ts_map = scan_brain_sessions(brain_dir, workspace)

    target_sids = [s.id for s in sessions if not s.is_subagent]
    if not target_sids:
        target_sids = [s.id for s in sessions]
    if session_id and session_id not in target_sids:
        target_sids.insert(0, session_id)

    canonical_images, canonical_mds = collect_canonical_artifacts(
        sessions, origin_map, authored_ts_map, local_notes_dir, workspace
    )
    sorted_docs = sort_canonical_docs(canonical_mds)

    if sync_hubs:
        sync_all_targets(
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

    hot_files = collect_hot_files(sessions, workspace, limit=8)
    rich_media_list = collect_rich_media(sessions, workspace)

    primary_sessions = [s for s in sessions if not s.is_subagent]
    subagent_sessions = [s for s in sessions if s.is_subagent]
    if not primary_sessions:
        primary_sessions = list(sessions)
        subagent_sessions = []

    active_sid = session_id if (session_id and any(s.id == session_id for s in sessions)) else ""
    if not active_sid and primary_sessions:
        active_sid = primary_sessions[0].id

    wt = git_state.working_tree
    cur_branch = git_state.current_branch or "detached"
    active_branch_obj = next(
        (b for b in git_state.branches if b.name == cur_branch),
        git_state.branches[0] if git_state.branches else None,
    )
    tip_sha = active_branch_obj.sha if active_branch_obj else ""

    ordered_sessions = sorted(
        sessions,
        key=lambda s: (s.tree_num, 1 if s.is_subagent else 0, s.fork_depth, s.first_step, s.first_ts_iso),
    )

    serialized_sessions: list[dict[str, Any]] = []
    for s in ordered_sessions:
        fstep = s.fork_step if s.fork_step is not None else -1
        traj: list[dict[str, Any]] = []
        prev_tok = 0
        for st in sorted(s.step_ctx_tokens.keys()):
            tok = s.step_ctx_tokens[st]
            if tok <= 0:
                continue
            compacted = bool(prev_tok > 60_000 and tok < prev_tok * 0.5)
            prev_tok = tok
            c_tok = s.step_cache_tokens.get(st, 0)
            o_tok = s.step_out_tokens.get(st, 0)
            t_list = s.step_tools.get(st, [])
            traj.append(
                {
                    "step": st,
                    "tokens": tok,
                    "cacheTokens": c_tok,
                    "inputTokens": max(0, tok - c_tok),
                    "outputTokens": o_tok,
                    "tools": t_list[:6],
                    "inherited": bool(s.parent_id and fstep >= 0 and st <= fstep),
                    "compacted": compacted,
                }
            )

        valid_authored = [a for a in (s.authored_docs or []) if a in canonical_mds]
        source_env = "cli" if "antigravity-cli" in str(s.path) else "ide"
        cur_ctx = s.current_ctx_tokens
        cur_cache = s.current_cache_tokens
        cur_input = s.current_input_tokens if s.current_input_tokens > 0 else max(0, cur_ctx - cur_cache)
        cache_hit_pct = round((cur_cache / cur_ctx) * 100) if cur_ctx > 0 else 0
        top_tools = [
            {"name": k, "count": v}
            for k, v in sorted(s.tool_counts.items(), key=lambda x: (-x[1], x[0]))[:8]
        ]
        total_tool_calls = sum(s.tool_counts.values())

        def _ctx_near_step(step_num: int) -> int:
            if step_num < 0:
                return 0
            for candidate in (step_num, step_num + 1, step_num + 2, step_num - 1):
                if candidate in s.step_ctx_tokens and s.step_ctx_tokens[candidate] > 0:
                    return s.step_ctx_tokens[candidate]
            return 0

        serialized_sessions.append(
            {
                "id": s.id,
                "shortId": s.id[:8],
                "title": s.title or ("Subagent Run" if s.is_subagent else "Untitled Session"),
                "source": source_env,
                "path": str(s.path),
                "hubPath": str(s.path / "PROJECT_HUB.md"),
                "isSubagent": s.is_subagent,
                "agentName": s.agent_name,
                "treeNum": s.tree_num,
                "parentId": s.parent_id,
                "rootId": s.root_id,
                "forkDepth": s.fork_depth,
                "forkStep": s.fork_step,
                "lineageSource": s.lineage_source,
                "firstStep": s.first_step,
                "lastStep": s.last_step,
                "stepSpan": max(0, s.last_step - s.first_step + 1),
                "startedLocal": s.started_local,
                "lastActive": s.last_active,
                "lastTsIso": s.last_ts_iso,
                "mtime": s.mtime,
                "userChats": s.user_chats,
                "inheritedChats": s.inherited_chats,
                "totalChats": s.user_chats + s.inherited_chats,
                "currentCtxTokens": cur_ctx,
                "currentCtxFormatted": format_tokens(cur_ctx),
                "cacheReadTokens": cur_cache,
                "cacheReadFormatted": format_tokens(cur_cache),
                "freshInputTokens": cur_input,
                "freshInputFormatted": format_tokens(cur_input),
                "cacheHitPct": cache_hit_pct,
                "peakCtxTokens": s.peak_ctx_tokens,
                "peakCtxFormatted": format_tokens(s.peak_ctx_tokens),
                "totalOutputTokens": s.total_output_tokens,
                "totalOutputFormatted": format_tokens(s.total_output_tokens),
                "totalToolCalls": total_tool_calls,
                "topTools": top_tools,
                "compactionCount": s.compaction_count,
                "inheritedCompactions": s.inherited_compactions,
                "authoredDocs": valid_authored,
                "touchedFiles": [
                    {"rel": t.rel, "abs": t.abs, "tsLocal": t.ts_local}
                    for t in list(s.touched_files.values())[:10]
                ],
                "prompts": [
                    {
                        "step": p.step,
                        "timestamp": p.timestamp,
                        "text": p.text,
                        "ctxTokens": _ctx_near_step(p.step),
                        "ctxFormatted": format_tokens(_ctx_near_step(p.step)) if _ctx_near_step(p.step) > 0 else "",
                    }
                    for p in s.prompts
                ],
                "trajectory": traj,
            }
        )

    serialized_docs: list[dict[str, Any]] = []
    for d in sorted_docs:
        local_shortcut = local_notes_dir / d.name
        serialized_docs.append(
            {
                "name": d.name,
                "title": d.title or d.name,
                "category": d.category,
                "summary": d.summary or d.purpose,
                "updatedStr": d.updated_str,
                "originSid": d.origin_sid,
                "lineCount": d.stats.line_count,
                "visualCount": d.stats.visual_count,
                "sections": d.stats.h2s[:5],
                "localPath": str(local_shortcut if local_shortcut.exists() else d.path),
                "brainPath": str(d.brain_path or d.path),
            }
        )

    serialized_media: list[dict[str, Any]] = []
    for item in rich_media_list:
        ts_str = dt.datetime.fromtimestamp(item.mtime).strftime("%Y-%m-%d %H:%M")
        serialized_media.append(
            {
                "name": item.name,
                "path": str(item.path),
                "relLabel": item.rel_label,
                "ext": item.ext,
                "sizeStr": format_size(item.size_bytes),
                "originSid": item.origin_sid,
                "updatedLocal": ts_str,
            }
        )

    return {
        "workspace": {
            "name": workspace.name,
            "path": str(workspace),
            "localNotesHubPath": str(local_notes_dir / "PROJECT_HUB.md"),
            "syncedAt": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "activeSessionId": active_sid,
        "kpis": {
            "docCount": len(sorted_docs),
            "totalDocLines": sum(d.stats.line_count for d in sorted_docs),
            "totalDocVisuals": sum(d.stats.visual_count for d in sorted_docs),
            "richMediaCount": len(rich_media_list),
            "primarySessionCount": len(primary_sessions),
            "rootTreeCount": len({s.root_id for s in primary_sessions}),
            "forkCount": sum(1 for s in primary_sessions if s.parent_id),
            "subagentCount": len(subagent_sessions),
            "totalChats": sum(s.user_chats for s in primary_sessions),
            "totalSteps": sum(max(0, s.last_step - s.first_step + 1) for s in sessions),
            "totalOutputTokens": sum(s.total_output_tokens for s in sessions),
            "totalOutputFormatted": format_tokens(sum(s.total_output_tokens for s in sessions)),
        },
        "git": {
            "currentBranch": cur_branch,
            "tipSha": tip_sha,
            "clean": wt.clean,
            "modified": wt.modified,
            "added": wt.added,
            "deleted": wt.deleted,
            "untracked": wt.untracked,
            "insertions": wt.insertions,
            "deletions": wt.deletions,
            "changedFiles": [
                {
                    "rel": f.rel,
                    "abs": f"/{f.abs}" if not f.abs.startswith("/") and ":" not in f.abs[:3] else f.abs,
                    "badge": f.badge,
                }
                for f in wt.files[:24]
            ],
            "branches": [
                {"name": b.name, "sha": b.sha, "subject": b.subject, "active": b.name == cur_branch}
                for b in git_state.branches
            ],
            "commits": [
                {
                    "sha": c.sha,
                    "parents": c.parents,
                    "date": c.date,
                    "author": c.author,
                    "refs": c.refs,
                    "subject": c.subject,
                }
                for c in git_state.commits[:16]
            ],
            "graphCommits": [
                {
                    "sha": c.sha,
                    "parents": c.parents,
                    "date": c.date,
                    "author": c.author,
                    "refs": c.refs,
                    "subject": c.subject,
                }
                for c in (git_state.graph_commits or git_state.commits)[:45]
            ],
        },
        "hotFiles": [
            {"rel": h.rel, "abs": h.abs, "tsLocal": h.ts_local, "sessionId": h.session_id}
            for h in hot_files
        ],
        "artifacts": serialized_docs,
        "richMedia": serialized_media,
        "sessions": serialized_sessions,
    }


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

    target_sids = [s.id for s in sessions if not s.is_subagent]
    if not target_sids:
        target_sids = [s.id for s in sessions]
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


def run_from_hook(hook_event: str, script_path: Path | None = None) -> None:
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
            target_script = script_path or (Path(__file__).resolve().parent.parent / "sync_local_notes.py")
            cmd = [
                sys.executable,
                str(target_script),
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


def main(argv: list[str] | None = None) -> None:
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
        "--dump-json",
        action="store_true",
        help="Output structured JSON telemetry payload to stdout (for VS Code extension)",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="When used with --dump-json, skip writing PROJECT_HUB.md files and only compute telemetry",
    )
    parser.add_argument(
        "--from-hook",
        type=str,
        choices=["post_invocation", "post_tool", "stop"],
        default="",
        help="Internal lifecycle hook mode ('post_invocation', 'post_tool', or 'stop')",
    )
    args = parser.parse_args(argv)

    if args.from_hook:
        run_from_hook(args.from_hook)
        return

    workspace = Path(args.workspace).resolve()
    brain_dir = (
        Path(args.brain_dir).expanduser().resolve()
        if args.brain_dir
        else resolve_default_brain_dir(args.session_id).resolve()
    )
    if args.dump_json:
        payload = build_telemetry_payload(
            workspace,
            brain_dir,
            session_id=args.session_id,
            sync_hubs=not args.no_sync,
        )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return

    run_sync(workspace, brain_dir, session_id=args.session_id, quiet=args.quiet)
