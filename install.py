#!/usr/bin/env python3
"""Install or update the `local-recap` skill in `~/.gemini/config/skills/local-recap`."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def configure_vscode_editor_associations() -> list[Path]:
    """Configure VS Code's `workbench.editorAssociations` so `.local-notes/*.md` shortcuts
    open automatically in the Antigravity Artifact Viewer (`antigravity.artifactEditor`).
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

    updated: list[Path] = []
    for settings_path in candidates:
        if not settings_path.parent.exists():
            continue
        data: dict = {}
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
            settings_path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8", newline="\n")
        updated.append(settings_path)
    return updated


def register_lifecycle_hooks(config_root: Path, py_cmd: str, installed_script: Path) -> Path:
    """Register `local-recap-auto-sync` in `~/.gemini/config/hooks.json` so `PROJECT_HUB.md`
    and `.local-notes/` shortcuts are automatically updated whenever brain artifacts are modified.
    """
    hooks_file = config_root / "hooks.json"
    hooks_data: dict = {}
    if hooks_file.exists():
        try:
            loaded = json.loads(hooks_file.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(loaded, dict):
                hooks_data = loaded
        except Exception:
            pass

    hooks_data["local-recap-auto-sync"] = {
        "enabled": True,
        "PostInvocation": [
            {
                "type": "command",
                "command": f'{py_cmd} "{installed_script}" --from-hook post_invocation',
                "timeout": 10,
            }
        ],
        "PostToolUse": [
            {
                "matcher": "write_file|edit_file|write_to_file|replace_file_content|multi_replace_file_content",
                "hooks": [
                    {
                        "type": "command",
                        "command": f'{py_cmd} "{installed_script}" --from-hook post_tool',
                        "timeout": 10,
                    }
                ],
            }
        ],
        "Stop": [
            {
                "type": "command",
                "command": f'{py_cmd} "{installed_script}" --from-hook stop',
                "timeout": 10,
            }
        ],
    }
    hooks_file.write_text(json.dumps(hooks_data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return hooks_file


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    config_root = Path.home() / ".gemini" / "config"
    target_dir = config_root / "skills" / "local-recap"
    target_dir.mkdir(parents=True, exist_ok=True)

    items = [
        ("SKILL.md", target_dir / "SKILL.md"),
        ("scripts/sync_local_notes.py", target_dir / "scripts" / "sync_local_notes.py"),
        ("resources/viz_template.html", target_dir / "resources" / "viz_template.html"),
    ]
    for rel_src, dst in items:
        src = repo_root / rel_src
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        print(f"Installed: {dst}")

    installed_skill_md = target_dir / "SKILL.md"
    installed_script = target_dir / "scripts" / "sync_local_notes.py"
    py_cmd = "python" if os.name == "nt" else "python3"
    skill_text = installed_skill_md.read_text(encoding="utf-8", errors="ignore")
    skill_text = skill_text.replace(
        'python3 "$HOME/.gemini/config/skills/local-recap/scripts/sync_local_notes.py"',
        f'{py_cmd} "{installed_script}"',
    )
    installed_skill_md.write_text(skill_text, encoding="utf-8", newline="\n")

    hooks_file = register_lifecycle_hooks(config_root, py_cmd, installed_script)
    print(f"Configured auto-sync hooks: {hooks_file}")
    for vs_cfg in configure_vscode_editor_associations():
        print(f"Configured Antigravity Artifact Viewer associations: {vs_cfg}")
    print(f"\nSkill 'local-recap' is ready at: {target_dir}")


if __name__ == "__main__":
    main()
