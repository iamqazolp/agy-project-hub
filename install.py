#!/usr/bin/env python3
"""Install or update the `local-recap` skill and the `Antigravity Markdown Review` VS Code extension."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path


EXT_ID = "iamqazolp.agy-markdown-review"
EXT_VERSION = "1.0.0"
EXT_DIR_NAME = f"{EXT_ID}-{EXT_VERSION}"


def install_vscode_extension(repo_root: Path) -> list[Path]:
    """Install the bundled `vscode-extension` into `~/.vscode/extensions/` (and Cursor/Antigravity if present)
    and register it in `extensions.json`. Also pre-syncs Markdown Preview Enhanced (`~/.local/state/crossnote`).
    """
    ext_src = repo_root / "vscode-extension"
    if not ext_src.exists():
        return []

    home = Path.home()
    ext_roots = [
        home / ".vscode" / "extensions",
        home / ".antigravity" / "extensions",
        home / ".cursor" / "extensions",
    ]

    installed_paths: list[Path] = []
    for idx, root in enumerate(ext_roots):
        if idx > 0 and not root.exists():
            continue
        root.mkdir(parents=True, exist_ok=True)
        target = root / EXT_DIR_NAME
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(ext_src, target)
        installed_paths.append(target)

        # Register in extensions.json if present
        manifest_path = root / "extensions.json"
        entries: list = []
        if manifest_path.exists():
            try:
                loaded = json.loads(manifest_path.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(loaded, list):
                    entries = [
                        e
                        for e in loaded
                        if not (isinstance(e, dict) and e.get("identifier", {}).get("id") == EXT_ID)
                    ]
            except Exception:
                entries = []

        target_posix = target.as_posix()
        entries.append(
            {
                "identifier": {"id": EXT_ID},
                "version": EXT_VERSION,
                "location": {
                    "$mid": 1,
                    "fsPath": str(target),
                    "external": f"file://{target_posix}",
                    "path": target_posix,
                    "scheme": "file",
                },
                "relativeLocation": EXT_DIR_NAME,
                "metadata": {
                    "installedTimestamp": int(time.time() * 1000),
                    "pinned": False,
                    "source": "vsix",
                    "publisherDisplayName": "iamqazolp",
                    "targetPlatform": "undefined",
                    "updated": False,
                    "private": False,
                    "isPreReleaseVersion": False,
                    "hasPreReleaseVersion": False,
                },
            }
        )
        manifest_path.write_text(json.dumps(entries), encoding="utf-8", newline="\n")

    # Also pre-sync Crossnote (Markdown Preview Enhanced) style.less if crossnote is used
    try:
        crossnote_dir = home / ".local" / "state" / "crossnote"
        crossnote_dir.mkdir(parents=True, exist_ok=True)
        css_text = (ext_src / "media" / "antigravity-markdown.css").read_text(encoding="utf-8")
        style_less = crossnote_dir / "style.less"
        begin_marker = "/* BEGIN ANTIGRAVITY MARKDOWN STYLE */"
        end_marker = "/* END ANTIGRAVITY MARKDOWN STYLE */"
        block = f"{begin_marker}\n{css_text}\n{end_marker}"
        existing = style_less.read_text(encoding="utf-8", errors="ignore") if style_less.exists() else ""
        if begin_marker in existing and end_marker in existing:
            s_idx = existing.index(begin_marker)
            e_idx = existing.index(end_marker) + len(end_marker)
            existing = existing[:s_idx] + block + existing[e_idx:]
        else:
            existing = existing.rstrip() + "\n\n" + block + "\n"
        style_less.write_text(existing, encoding="utf-8", newline="\n")
    except Exception:
        pass

    return installed_paths


def configure_vscode_editor_associations() -> list[Path]:
    """Configure VS Code's `workbench.editorAssociations` so Markdown files and `.local-notes/*.md`
    shortcuts open in Antigravity style by default.
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

    desired = {
        "*.md": "antigravity.markdownReview",
        "**/.local-notes/*.md": "antigravity.markdownReview",
        "**/.local-notes/**/*.md": "antigravity.markdownReview",
        "**/.gemini/*/brain/**/*.md": "antigravity.artifactEditor",
    }

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
        for pattern, editor_id in desired.items():
            if assoc.get(pattern) != editor_id:
                assoc[pattern] = editor_id
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

    for ext_dir in install_vscode_extension(repo_root):
        print(f"Installed VS Code extension: {ext_dir}")

    for vs_cfg in configure_vscode_editor_associations():
        print(f"Configured Antigravity Markdown associations: {vs_cfg}")

    print(f"\nSkill 'local-recap' and 'Antigravity Markdown Review' extension are ready!")


if __name__ == "__main__":
    main()
