#!/usr/bin/env python3
"""Install or update the `local-recap` skill in `~/.gemini/config/skills/local-recap`."""

from __future__ import annotations

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

    print(f"\nSkill 'local-recap' is ready at: {target_dir}")


if __name__ == "__main__":
    main()
