#!/usr/bin/env python3
"""Install or update the `local-recap` skill in `~/.gemini/config/skills/local-recap`."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


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
    print(f"\nSkill 'local-recap' is ready at: {target_dir}")


if __name__ == "__main__":
    main()
