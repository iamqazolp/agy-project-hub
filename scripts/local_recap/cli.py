"""CLI entrypoint, workspace sync orchestration, and Antigravity lifecycle hook runner for `local-recap`."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .artifact_sync import (
    collect_canonical_artifacts,
    ensure_vscode_editor_associations,
    sort_canonical_docs,
    sync_local_shortcuts,
)
from .git_telemetry import collect_git_state, ensure_git_exclude
from .hub_renderer import sync_all_targets
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
    run_sync(workspace, brain_dir, session_id=args.session_id, quiet=args.quiet)
