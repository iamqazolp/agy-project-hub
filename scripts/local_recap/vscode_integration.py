"""VS Code editor associations and CLI/IDE brain directory bridging."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def ensure_vscode_editor_associations(workspace: Path | None = None) -> None:
    """Ensure VS Code's `workbench.editorAssociations` maps `.local-notes/*.md` shortcuts
    to `antigravity.markdownReview` (or `antigravity.artifactEditor`) so clicking them in
    the VS Code Explorer opens the Antigravity style instead of raw Markdown text.
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

    has_agy_md_ext = (home / ".vscode" / "extensions" / "iamqazolp.agy-markdown-review-1.0.0").exists()
    local_notes_editor = "antigravity.markdownReview" if has_agy_md_ext else "antigravity.artifactEditor"
    desired_assoc = {
        "**/.local-notes/*.md": local_notes_editor,
        "**/.local-notes/**/*.md": local_notes_editor,
        "**/.gemini/*/brain/**/*.md": "antigravity.artifactEditor",
    }
    if has_agy_md_ext:
        desired_assoc["*.md"] = "antigravity.markdownReview"

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
        for pattern, editor_id in desired_assoc.items():
            if assoc.get(pattern) != editor_id:
                assoc[pattern] = editor_id
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
