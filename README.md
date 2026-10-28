# ⚡ `agy-project-hub` (`local-recap` Skill)

A **zero-context-overhead** multi-session & fork management skill for **Google Antigravity**.

When running multiple concurrent sessions and forks on the same codebase, notes and artifacts get scattered across isolated `~/.gemini/antigravity-cli/brain/<conversation-id>/` directories, and opening `.md` files outside the active session's brain folder loses Antigravity's rich native Artifact Viewer styling.

`agy-project-hub` solves this with an out-of-context Python synchronizer (`scripts/sync_local_notes.py`) that:
1. **Syncs all Markdown notes & visual assets bidirectionally** across every session/fork of a workspace (`brain/<id>/*` $\leftrightarrow$ `<workspace>/.local-notes/notes/*`).
2. **Registers companion `<name>.md.metadata.json` files** in every active session's `brain/<id>/` directory so every note from every sibling session opens in **Antigravity's native styled Artifact Viewer**.
3. **Reconstructs the exact Multi-Root Session Fork Forest** and per-session telemetry (`Active Context`, `Peak Context`, `Compaction Count`, `Total Output Tokens`, `Chats & Steps`, `Start -> Last Active` local timestamps, and `Full Session UUIDs`) into `PROJECT_HUB.md`.
4. **Auto-excludes `.local-notes/` via `.git/info/exclude`** so target repositories stay 100% clean without modifying tracked `.gitignore` files.

---

## 🧠 Why It Uses ~0 Context Tokens in Your Sessions

1. **Progressive Disclosure (`~30 tokens` idle):** Antigravity only loads the 2-line YAML frontmatter of [`SKILL.md`](./SKILL.md) into the system prompt unless you explicitly ask to recap or sync notes. Even when activated, [`SKILL.md`](./SKILL.md) is only **22 lines (`~160 tokens`)**.
2. **100% Out-of-Context Execution (`0 LLM tokens` for scanning):** The agent never reads other sessions' transcripts into its own context window. Instead, [`scripts/sync_local_notes.py`](./scripts/sync_local_notes.py) runs as a standalone Python subprocess that parses SQLite metadata and `.system_generated/logs/transcript.jsonl` files on disk and writes `PROJECT_HUB.md` directly.

---

## 🌳 How Multi-Root & Fork Lineage Resolution Works

Even when a project has **multiple independent Root Sessions** (and forks whose step numbers collide across trees), [`scripts/sync_local_notes.py`](./scripts/sync_local_notes.py) resolves the exact lineage tree via a 3-stage pipeline:

1. **Stage 1 — Ground-Truth SQLite `parent_references` Decoding:**
   - Queries `~/.gemini/antigravity-cli/conversation_summaries.db` (`workspace_uris`, `title`) to discover all sessions belonging to the workspace (even brand-new root sessions that haven't mentioned the repo name in chat yet).
   - Reads `~/.gemini/antigravity-cli/conversations/<session-id>.db` $\rightarrow$ `parent_references`, decoding the protobuf wire format (`Field 6` = exact 36-char Parent Session UUID, `Field 2` varint = exact `fork_step` index, `Row 0` = ultimate `root_id`, `len(rows)` = `fork_depth`).
2. **Stage 2 — Transcript Header UUID Fallback:**
   - Scans the opening `transcript.jsonl` context summary and artifact paths for parent session UUIDs if the `.db` file is unavailable.
3. **Stage 3 — Step-Boundary Token + Timestamp Fingerprint Fallback:**
   - Matches the candidate parent whose cumulative context at `fork_step` (`input_tokens + cache_read_tokens + output_tokens`) matches the fork's opening context and occurred prior to the fork's start timestamp.

---

## 📦 Installation

Run the included installer to install (or update) the skill into `~/.gemini/config/skills/local-recap`:

```bash
python install.py
```

---

## 🚀 Usage

### Inside Antigravity Chat
Ask the agent naturally in any session:
- *"Recap our progress across all sessions and sync the hub"*
- *"Write a deep-dive note on `<topic>` and sync it to `.local-notes`"*
- *"Show me the session fork tree and context usage"*

### Standalone CLI
You can also run the synchronizer directly from any terminal:

```bash
python scripts/sync_local_notes.py --workspace /path/to/your/project --session-id <optional-current-session-uuid>
```

---

## 📁 Repository Structure

```text
agy-project-hub/
├── SKILL.md                      # Ultra-compact Antigravity skill definition (~22 lines)
├── install.py                    # Cross-platform installer to ~/.gemini/config/skills/local-recap
├── README.md                     # Architecture & usage guide
├── scripts/
│   └── sync_local_notes.py       # Out-of-context multi-session & fork synchronizer
└── resources/
    └── viz_template.html         # Dark-mode interactive HTML visualization template
```
