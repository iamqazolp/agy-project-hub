"""Artifact classification, canonical collection, rich media / hot-file discovery, and `.local-notes/` shortcut synchronization."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from .models import ArtifactDoc, DocStats, RichMediaItem, SessionInfo, TouchEvent

SKIP_MEDIA_DIRS = {
    ".local-notes",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "data",
    "raw",
    "datasets",
    "corpus",
    "cache",
    "logs",
    "tmp",
    "coverage",
    "htmlcov",
}


def extract_md_title(md_path: Path) -> str:
    """Extract the first H1 title (`# ...`) from a Markdown file, or fall back to its stem."""
    try:
        for line in md_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:
        pass
    return md_path.stem.replace("_", " ").title()


def classify_document(
    md_name: str, title: str, content: str, meta_summary: str = ""
) -> tuple[int, str, str]:
    """Condense all notes into 3 high-level categories:
    1. `📋 Recap`
    2. `📘 Deep Dive`
    3. `📐 Spec & Plan`
    """
    low = md_name.lower()
    if "recap" in low or "summary" in low or "status" in low or "changelog" in low:
        prio, cat = 1, "📋 Recap"
    elif any(k in low for k in ("briefing", "proposal", "plan", "spec", "roadmap", "rfc", "design")):
        prio, cat = 3, "📐 Spec & Plan"
    else:
        prio, cat = 2, "📘 Deep Dive"

    clean_meta = " ".join(meta_summary.splitlines()).strip()
    if clean_meta and not clean_meta.lower().startswith("synced from session"):
        if len(clean_meta) > 145:
            clean_meta = clean_meta[:142] + "..."
        return (prio, cat, clean_meta)

    first_para = ""
    for line in content.splitlines():
        s = line.strip()
        if s and not s.startswith(("#", "-", "*", "|", "!", "`", "---")):
            s = re.sub(r"^>\s*(\[![A-Z]+\])?\s*", "", s).strip()
            s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
            s = s.replace("**", "").replace("*", "")
            if len(s) > 20:
                first_para = s
                break
    if not first_para:
        first_para = title
    if len(first_para) > 145:
        first_para = first_para[:142] + "..."
    return (prio, cat, first_para)


def extract_md_sections_and_stats(content: str) -> DocStats:
    """Count lines, embedded images/mermaid diagrams, and extract up to 4 H2 section titles."""
    lines = content.splitlines()
    h2s: list[str] = []
    img_count = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", content))
    mermaid_count = len(re.findall(r"```mermaid", content))
    for line in lines:
        if line.startswith("## "):
            sec = line[3:].strip()
            sec = re.sub(r"^(Part\s+\d+:\s*|\d+\.\s*)", "", sec)
            sec = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", sec)
            sec = sec.replace("`", "").replace("*", "")
            sec = re.sub(r"\s*\([^)]*\)\s*$", "", sec).strip()
            if ":" in sec and len(sec) > 36:
                sec = sec.split(":", 1)[0].strip()
            h2s.append(sec)
    return DocStats(
        line_count=len(lines),
        h2s=h2s[:4],
        total_h2s=len(h2s),
        visual_count=img_count + mermaid_count,
    )


def write_artifact_metadata(
    md_file: Path,
    summary: str,
    origin_sid: str = "",
    updated_at_iso: str = "",
) -> None:
    """Write companion `<name>.md.metadata.json` so Antigravity renders `md_file` natively."""
    meta_path = md_file.parent / f"{md_file.name}.metadata.json"
    ts_iso = updated_at_iso or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f0Z")
    payload: dict[str, Any] = {
        "summary": summary,
        "updatedAt": ts_iso,
        "userFacing": True,
    }
    if origin_sid:
        payload["originSession"] = origin_sid
    new_json = json.dumps(payload, indent=2)
    if meta_path.exists():
        try:
            if meta_path.read_text(encoding="utf-8", errors="ignore").strip() == new_json.strip():
                return
        except Exception:
            pass
    meta_path.write_text(new_json, encoding="utf-8", newline="\n")


def rewrite_md_images_for_brain_dir(md_text: str, target_brain_dir: Path) -> str:
    """Rewrite any embedded image path (`.../brain/<any-id>/<img.png>` or `../assets/<img.png>`)
    to the exact absolute path inside `target_brain_dir`.
    """
    target_norm = str(target_brain_dir).replace("\\", "/")
    pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

    def _repl(match: re.Match[str]) -> str:
        alt = match.group(1)
        url = match.group(2).strip()
        clean_url = url.replace("\\", "/")
        if clean_url.lower().endswith((".png", ".svg", ".jpg", ".jpeg")):
            basename = clean_url.rsplit("/", 1)[-1]
            if (target_brain_dir / basename).exists():
                return f"![{alt}]({target_norm}/{basename})"
        return match.group(0)

    return pattern.sub(_repl, md_text)


def collect_canonical_artifacts(
    sessions: list[SessionInfo],
    origin_map: dict[str, str],
    authored_ts_map: dict[str, str],
    local_notes_dir: Path,
    workspace: Path,
) -> tuple[dict[str, Path], dict[str, ArtifactDoc]]:
    """Gather the newest version of every image and Markdown note across all `brain/*`
    sessions (and any legacy physical files in `<workspace>/.local-notes/`).
    """
    canonical_images: dict[str, Path] = {}
    canonical_mds: dict[str, ArtifactDoc] = {}

    for img_dir in (workspace / "docs" / "assets", local_notes_dir / "assets"):
        if img_dir.exists() and not img_dir.is_symlink():
            for img in img_dir.iterdir():
                if img.is_file() and not img.is_symlink() and img.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg"}:
                    canonical_images[img.name] = img

    def _consider_md(md_path: Path, fallback_sid: str, is_local_backup: bool = False) -> None:
        if md_path.is_symlink() or md_path.name in {"PROJECT_HUB.md", "INDEX.md"}:
            return
        meta_file = md_path.parent / f"{md_path.name}.metadata.json"
        meta_summary = ""
        meta_origin = ""
        if meta_file.exists():
            try:
                mobj = json.loads(meta_file.read_text(encoding="utf-8", errors="ignore"))
                meta_summary = str(mobj.get("summary") or "")
                meta_origin = str(mobj.get("originSession") or "")
            except Exception:
                pass

        # Skip previously-synced duplicate copies in non-origin brain folders when the original brain file exists
        if (
            not is_local_backup
            and meta_origin
            and meta_origin != fallback_sid
            and (md_path.parent.parent / meta_origin / md_path.name).exists()
        ):
            return

        mtime = md_path.stat().st_mtime
        existing = canonical_mds.get(md_path.name)
        if existing is not None:
            if is_local_backup and not existing.from_local_backup:
                return
            if existing.mtime >= mtime:
                return

        raw_content = md_path.read_text(encoding="utf-8", errors="ignore")
        title = extract_md_title(md_path)
        prio, category, purpose = classify_document(md_path.name, title, raw_content, meta_summary)
        stats = extract_md_sections_and_stats(raw_content)
        if is_local_backup:
            true_origin = origin_map.get(md_path.name) or meta_origin or fallback_sid
            brain_root = sessions[0].path.parent if sessions else md_path.parent
            orig_brain_path = brain_root / true_origin / md_path.name
        else:
            true_origin = meta_origin or fallback_sid or origin_map.get(md_path.name, "")
            orig_candidate = md_path.parent.parent / true_origin / md_path.name if true_origin else md_path
            orig_brain_path = orig_candidate if orig_candidate.exists() else md_path
        true_ts = authored_ts_map.get(md_path.name) or dt.datetime.fromtimestamp(mtime).strftime(
            "%Y-%m-%d %H:%M"
        )

        canonical_mds[md_path.name] = ArtifactDoc(
            name=md_path.name,
            path=md_path,
            brain_path=orig_brain_path,
            from_local_backup=is_local_backup,
            mtime=mtime,
            updated_str=true_ts,
            title=title,
            priority=prio,
            category=category,
            purpose=purpose,
            summary=meta_summary or purpose,
            origin_sid=true_origin,
            stats=stats,
        )

    for sess in sessions:
        for art in sess.artifacts:
            if art.is_symlink():
                continue
            ext = art.suffix.lower()
            if ext in {".png", ".svg", ".jpg", ".jpeg"}:
                prev_img = canonical_images.get(art.name)
                if prev_img is None or art.stat().st_mtime > prev_img.stat().st_mtime:
                    canonical_images[art.name] = art
            elif ext == ".md":
                _consider_md(art, sess.id, is_local_backup=False)

    default_sid = sessions[0].id if sessions else "local"
    for legacy_dir in (local_notes_dir, local_notes_dir / "notes"):
        if legacy_dir.exists() and not legacy_dir.is_symlink():
            for local_md in legacy_dir.glob("*.md"):
                if not local_md.is_symlink():
                    _consider_md(local_md, origin_map.get(local_md.name, default_sid), is_local_backup=True)

    return canonical_images, canonical_mds


def sort_canonical_docs(canonical_mds: dict[str, ArtifactDoc]) -> list[ArtifactDoc]:
    """Deterministically sort canonical documents by category priority, newest timestamp/mtime, and filename."""
    docs = sorted(canonical_mds.values(), key=lambda d: d.name)
    docs.sort(key=lambda d: (d.updated_str or "", d.mtime or 0.0), reverse=True)
    docs.sort(key=lambda d: d.priority)
    return docs


def collect_hot_files(
    sessions: list[SessionInfo], workspace: Path, limit: int = 5
) -> list[TouchEvent]:
    """Return the `limit` most recently edited workspace source files across all sessions."""
    merged_touched: dict[str, TouchEvent] = {}
    for s in sessions:
        for rel_f, tinfo in (s.touched_files or {}).items():
            if rel_f in {"PROJECT_HUB.md", "INDEX.md"} or rel_f.startswith(".local-notes/"):
                continue
            if not (workspace / rel_f).exists():
                continue
            prev_t = merged_touched.get(rel_f)
            if prev_t is None or (tinfo.ts_iso or "") >= (prev_t.ts_iso or ""):
                merged_touched[rel_f] = tinfo
    return sorted(
        merged_touched.values(),
        key=lambda x: x.ts_iso or "",
        reverse=True,
    )[:limit]


def collect_rich_media(sessions: list[SessionInfo], workspace: Path) -> list[RichMediaItem]:
    """Discover authored interactive `.html` apps/visualizations and `.pdf` exports across `brain/` and `workspace`."""
    rich_media_map: dict[str, RichMediaItem] = {}
    for s in sessions:
        for art in s.artifacts or []:
            if art.is_symlink() or not art.is_file():
                continue
            ext = art.suffix.lower()
            if ext in {".html", ".pdf"} and art.name.lower() != "index.html":
                mtime = art.stat().st_mtime
                prev_m = rich_media_map.get(art.name)
                if prev_m is None or mtime > prev_m.mtime:
                    rich_media_map[art.name] = RichMediaItem(
                        name=art.name,
                        path=art.resolve(),
                        rel_label=f"brain/{s.id[:8]}/{art.name}",
                        ext=ext,
                        mtime=mtime,
                        size_bytes=art.stat().st_size,
                        origin_sid=s.id,
                    )
    if workspace.exists():
        for root_dir, dirnames, filenames in os.walk(workspace):
            rel_dir = Path(root_dir).resolve().relative_to(workspace.resolve())
            depth = len(rel_dir.parts)
            dirnames[:] = [
                d
                for d in dirnames
                if d not in SKIP_MEDIA_DIRS
                and not d.startswith(".")
                and not d.startswith("vscode-")
                and depth < 2
            ]
            for fname in filenames:
                fpath = Path(root_dir) / fname
                if fpath.is_symlink() or not fpath.is_file():
                    continue
                ext = fpath.suffix.lower()
                if ext in {".html", ".pdf"} and fname.lower() not in {"index.html", "theme_preview.html"}:
                    mtime = fpath.stat().st_mtime
                    rel_str = str(fpath.resolve().relative_to(workspace.resolve())).replace("\\", "/")
                    prev_m = rich_media_map.get(fname)
                    if prev_m is None or mtime >= prev_m.mtime - 60:
                        rich_media_map[fname] = RichMediaItem(
                            name=fname,
                            path=fpath.resolve(),
                            rel_label=rel_str,
                            ext=ext,
                            mtime=mtime,
                            size_bytes=fpath.stat().st_size,
                            origin_sid=prev_m.origin_sid if prev_m else "",
                        )
    return sorted(
        rich_media_map.values(),
        key=lambda m: (0 if m.ext == ".html" else 1, -m.mtime, m.name),
    )


def _write_text_preserving_mtime(dst: Path, content: str, mtime: float | None = None) -> None:
    """Write `content` to `dst` only if changed or missing, and preserve `mtime` when provided."""
    changed = True
    if dst.exists():
        try:
            if dst.read_text(encoding="utf-8", errors="ignore") == content:
                changed = False
        except Exception:
            pass
    if changed:
        dst.write_text(content, encoding="utf-8", newline="\n")
        if mtime is not None:
            try:
                os.utime(dst, (mtime, mtime))
            except Exception:
                pass
    elif mtime is not None and dst.exists():
        try:
            if abs(dst.stat().st_mtime - mtime) > 1.0:
                os.utime(dst, (mtime, mtime))
        except Exception:
            pass


def _create_file_shortcut(src_brain_file: Path, dst_shortcut: Path) -> None:
    """Create a symlink shortcut at `dst_shortcut` pointing directly to `src_brain_file`."""
    src_resolved = src_brain_file.resolve()
    if dst_shortcut.is_symlink() or dst_shortcut.exists():
        try:
            if dst_shortcut.is_symlink() and dst_shortcut.resolve() == src_resolved:
                return
        except Exception:
            pass
        dst_shortcut.unlink(missing_ok=True)
    try:
        os.symlink(src_resolved, dst_shortcut)
    except OSError:
        try:
            os.link(src_resolved, dst_shortcut)
        except OSError:
            norm_target = str(src_resolved).replace("\\", "/").lstrip("/")
            dst_shortcut.write_text(
                f"# Shortcut -> [{src_resolved.name}](file:///{norm_target})\n",
                encoding="utf-8",
                newline="\n",
            )


def sync_local_shortcuts(
    local_notes_dir: Path,
    primary_brain_dir: Path,
    sorted_docs: list[ArtifactDoc],
    sessions: list[SessionInfo],
) -> None:
    """Populate `<workspace>/.local-notes/` exclusively with shortcuts pointing to the
    original files in `brain/` (including `PROJECT_HUB.md`), and remove legacy physical copies.
    """
    local_notes_dir.mkdir(parents=True, exist_ok=True)

    for legacy_sub in ("notes", "assets"):
        sub_path = local_notes_dir / legacy_sub
        if sub_path.is_symlink():
            sub_path.unlink(missing_ok=True)
        elif sub_path.is_dir():
            shutil.rmtree(sub_path, ignore_errors=True)

    viz_sub = local_notes_dir / "viz"
    if viz_sub.is_dir() and not viz_sub.is_symlink():
        for html_f in viz_sub.glob("*.html"):
            if not html_f.is_symlink() and primary_brain_dir.exists():
                dst_brain_html = primary_brain_dir / html_f.name
                if not dst_brain_html.exists():
                    shutil.copy2(html_f, dst_brain_html)
        shutil.rmtree(viz_sub, ignore_errors=True)

    for legacy_file in ("INDEX.md", "index.html"):
        lf = local_notes_dir / legacy_file
        if lf.exists() or lf.is_symlink():
            lf.unlink(missing_ok=True)

    expected_names: set[str] = set()

    primary_hub = primary_brain_dir / "PROJECT_HUB.md"
    if primary_hub.exists():
        _create_file_shortcut(primary_hub, local_notes_dir / "PROJECT_HUB.md")
        expected_names.add("PROJECT_HUB.md")

    for doc in sorted_docs:
        orig_brain_path = Path(doc.brain_path or (primary_brain_dir.parent / doc.origin_sid / doc.name))
        if orig_brain_path.exists():
            _create_file_shortcut(orig_brain_path, local_notes_dir / doc.name)
            expected_names.add(doc.name)

    for sess in sessions:
        for art in sess.artifacts:
            if not art.is_symlink() and art.suffix.lower() == ".html" and art.exists():
                _create_file_shortcut(art, local_notes_dir / art.name)
                expected_names.add(art.name)

    for item in local_notes_dir.iterdir():
        if item.name not in expected_names:
            if item.is_symlink() or (item.is_file() and item.suffix.lower() in {".md", ".html"}):
                item.unlink(missing_ok=True)


def ensure_vscode_editor_associations(workspace: Path | None = None) -> None:
    """Ensure VS Code's `workbench.editorAssociations` maps `.md` files (including `.local-notes/*.md`
    and `brain/**/*.md`) to `antigravity.markdownReview` (`iamqazolp.agy-markdown-review`) instead of
    the legacy `antigravity.artifactEditor`.
    """
    home = Path.home()
    candidates: list[Path] = []
    if sys.platform == "darwin":
        app_support = home / "Library" / "Application Support"
        candidates = [
            app_support / "Code" / "User" / "settings.json",
            app_support / "Cursor" / "User" / "settings.json",
        ]
    elif os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        candidates = [
            appdata / "Code" / "User" / "settings.json",
            appdata / "Cursor" / "User" / "settings.json",
        ]
    else:
        cfg = home / ".config"
        candidates = [
            cfg / "Code" / "User" / "settings.json",
            cfg / "Cursor" / "User" / "settings.json",
        ]
    if workspace and (workspace / ".vscode" / "settings.json").exists():
        candidates.append(workspace / ".vscode" / "settings.json")

    for settings_path in candidates:
        if not settings_path.exists():
            continue
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8", errors="ignore"))
            if not isinstance(loaded, dict):
                continue
        except Exception:
            continue
        assoc = loaded.get("workbench.editorAssociations")
        if not isinstance(assoc, dict):
            assoc = {}
        changed = False
        target_editor = (
            "antigravity.artifactEditor"
            if "Antigravity" in str(settings_path)
            else "antigravity.markdownReview"
        )
        for pattern in ("*.md", "**/*.md", "**/.local-notes/*.md", "**/.local-notes/**/*.md", "**/.gemini/*/brain/**/*.md"):
            if assoc.get(pattern) != target_editor:
                assoc[pattern] = target_editor
                changed = True
        if changed:
            loaded["workbench.editorAssociations"] = assoc
            try:
                settings_path.write_text(json.dumps(loaded, indent=4) + "\n", encoding="utf-8", newline="\n")
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
