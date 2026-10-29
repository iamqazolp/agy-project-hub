---
name: local-recap
description: Syncs multi-session notes, fork lineage, and context/session telemetry across concurrent sessions into the active Antigravity brain directory and git-ignored .local-notes/ shortcuts. Activate whenever asked to recap progress, write or update any Markdown (.md) note/guide/deep-dive/plan/report, save visualizations, or check session/fork status.
---

# Local Recap & Multi-Session Sync (`local-recap`)

All heavy lifting (transcript scanning, fork tree detection, token/context calculation, `PROJECT_HUB.md` generation, and `.local-notes/` shortcut creation) runs out-of-context via `sync_local_notes.py` so session context overhead stays near zero.

## Workflow (Mandatory Whenever Creating or Updating Any `.md` Artifact)

1. **Write or update notes/visualizations in `brain/`** at `<appDataDir>/brain/<conversation-id>/<topic_name>.md` (with `ArtifactMetadata`) or `<appDataDir>/brain/<conversation-id>/<viz_name>.html`. Wait for `write_file` / `edit_file` to complete before step 2 (do **not** run step 2 in parallel in the same tool-call batch).
2. **Always run `sync_local_notes.py` immediately after** to regenerate `PROJECT_HUB.md` (with direct links to the original `brain/` files) and populate `<workspace>/.local-notes/` with shortcuts (including `.local-notes/PROJECT_HUB.md` and `.local-notes/<topic_name>.md`):
   ```bash
   python3 "$HOME/.gemini/config/skills/local-recap/scripts/sync_local_notes.py" --workspace "<workspace_path>" --session-id "<current_conversation_id>"
   ```
3. **Refresh `PROJECT_HUB.md` in UI** by touching `<appDataDir>/brain/<conversation-id>/PROJECT_HUB.md` with `edit_file` + `ArtifactMetadata`.
