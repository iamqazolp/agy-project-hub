#!/usr/bin/env python3
"""Install or update the `local-recap` skill in `~/.gemini/config/skills/local-recap`."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    target_dir = Path.home() / ".gemini" / "config" / "skills" / "local-recap"
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

    print(f"\nSkill 'local-recap' is ready at: {target_dir}")


if __name__ == "__main__":
    main()
