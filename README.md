# agy-project-hub (`local-recap`)

If you run multiple sessions or forks on the same project in Google Antigravity, your notes, plans, and deep dives end up scattered across random `~/.gemini/antigravity-cli/brain/<session-id>/` folders. Worse, if you copy those `.md` files into your workspace to keep track of them, VS Code opens them as plain text instead of using Antigravity's styled Artifact Viewer.

`agy-project-hub` fixes this without burning your context window.

It drops a lightweight `.local-notes/` folder into your project containing shortcuts back to the original brain artifacts, and keeps a single `PROJECT_HUB.md` dashboard updated with every note, session, fork tree, and context token count across the repo.

## What it does

- **Shortcuts instead of copies:** `.local-notes/` holds symlinks pointing straight to the original files in `brain/<session-id>/` (including `PROJECT_HUB.md`), so there is only ever one source of truth.
- **Keeps the Antigravity style in VS Code:** Automatically sets up VS Code's `workbench.editorAssociations` (`antigravity.artifactEditor`) and bridges CLI/IDE brain folders so clicking any shortcut in `.local-notes/` or any link inside `PROJECT_HUB.md` opens in the native Antigravity Artifact Viewer.
- **Updates automatically in the background:** Registers lightweight `PostInvocation`, `PostToolUse`, and `Stop` hooks in `~/.gemini/config/hooks.json`. Even if the agent forgets to update the hub, the hook updates `PROJECT_HUB.md` and conversation/context usage after every turn.
- **Zero context overhead:** All transcript scanning, SQLite lineage decoding, and file syncing happen in an external Python script (`scripts/sync_local_notes.py`). It costs `0` LLM tokens when idle or running in hooks.
- **Doesn't pollute git:** Adds `.local-notes/` to `.git/info/exclude` locally so your tracked `.gitignore` stays untouched.

## Installation

```bash
git clone https://github.com/iamqazolp/agy-project-hub.git
cd agy-project-hub
python3 install.py
```

Nevermind, just ask your Antigravity agent to install the skill for you. You just give it the repo link and wait 10 minutes.

## Usage

Once installed, everything syncs automatically at the end of each turn. Just open `.local-notes/PROJECT_HUB.md` from your VS Code file explorer to see:

1. **Knowledge Base:** Every Markdown note and visualization across all sessions for the project, grouped into Recaps, Deep Dives, and Specs/Plans.
2. **Session & Fork Telemetry:** A Mermaid fork tree and table showing every root session, fork, and subagent, along with active/peak context usage, chat counts, and clickable `conversation://` links.
3. **Recent Prompts & Git State:** The last few prompts per session so you remember what each fork was doing, plus current branch tips.

You can also ask the agent directly in chat:
- *"Recap our progress across all sessions"*
- *"Write a deep-dive note on the data pipeline and sync local notes"*

Or run the sync script manually from a terminal:

```bash
python3 ~/.gemini/config/skills/local-recap/scripts/sync_local_notes.py --workspace /path/to/repo
```

## How fork lineage is reconstructed

When you have multiple root sessions and forks on the same repo, `sync_local_notes.py` figures out which session forked from where in three steps:

1. **SQLite `parent_references`:** Reads `~/.gemini/antigravity-cli/conversation_summaries.db` and `conversations/<session-id>.db` to decode the exact parent UUID and fork step.
2. **Transcript references:** Falls back to scanning opening context summaries in `transcript.jsonl` if the `.db` entry isn't available.
3. **Token + timestamp fingerprinting:** Matches cumulative token counts (`input + cache_read + output`) at the fork step against candidate parent sessions.

## Files

```text
agy-project-hub/
├── SKILL.md                      # Skill instructions loaded by Antigravity (~22 lines)
├── install.py                    # Installs the skill, hooks, and VS Code editor associations
├── README.md                     # This file
├── scripts/
│   └── sync_local_notes.py       # Background sync & lineage reconstruction script
└── resources/
    └── viz_template.html         # HTML template for standalone diagrams
```
