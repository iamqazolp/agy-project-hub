---
name: local-recap
description: Syncs multi-session notes, fork lineage, and context/session telemetry across concurrent sessions into the active Antigravity brain directory and git-ignored .local-notes/. Use when asked to recap progress, save notes/visualizations, or check session/fork status.
---

# Local Recap & Multi-Session Sync (`local-recap`)

All heavy lifting (transcript scanning, fork tree detection, token/context calculation, and bidirectional artifact syncing) runs out-of-context via `sync_local_notes.py` so session context overhead stays near zero.

## Workflow

1. **Write or update notes/visualizations** in `<appDataDir>/brain/<conversation-id>/<topic_name>.md` (with `ArtifactMetadata`) or `<workspace>/.local-notes/viz/<viz_name>.html`.
2. **Run the sync script** to sync all sessions, reconstruct the fork tree & telemetry, and regenerate `PROJECT_HUB.md`:
   ```bash
   python3 "$HOME/.gemini/config/skills/local-recap/scripts/sync_local_notes.py" --workspace "<workspace_path>" --session-id "<current_conversation_id>"
   ```
3. **Refresh `PROJECT_HUB.md` in UI** by touching `<appDataDir>/brain/<conversation-id>/PROJECT_HUB.md` with `edit_file` + `ArtifactMetadata`.
