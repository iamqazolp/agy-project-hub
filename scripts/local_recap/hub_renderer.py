"""`PROJECT_HUB.md` generation, companion `.md.metadata.json` writer, and `.local-notes/` symlink shortcuts."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from .scanner import format_tokens, sort_canonical_docs
from .vscode_integration import bridge_ide_and_cli_brain_sessions


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
    sorted_docs: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
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
        orig_brain_path = Path(doc.get("brain_path") or (primary_brain_dir.parent / doc["origin_sid"] / doc["name"]))
        if orig_brain_path.exists():
            _create_file_shortcut(orig_brain_path, local_notes_dir / doc["name"])
            expected_names.add(doc["name"])

    for sess in sessions:
        for art in sess["artifacts"]:
            if not art.is_symlink() and art.suffix.lower() == ".html" and art.exists():
                _create_file_shortcut(art, local_notes_dir / art.name)
                expected_names.add(art.name)

    for item in local_notes_dir.iterdir():
        if item.name not in expected_names:
            if item.is_symlink() or (item.is_file() and item.suffix.lower() in {".md", ".html"}):
                item.unlink(missing_ok=True)


def sync_all_targets(
    sessions: list[dict[str, Any]],
    canonical_images: dict[str, Path],
    canonical_mds: dict[str, dict[str, Any]],
    workspace: Path,
    git_state: dict[str, Any],
    target_session_ids: list[str],
    brain_dir: Path,
) -> list[Path]:
    """Ensure canonical artifacts exist in their origin `brain/<id>/` folder and generate `PROJECT_HUB.md`."""
    sorted_docs = sort_canonical_docs(canonical_mds)
    all_sids = list({s["id"] for s in sessions} | set(target_session_ids) | {d["origin_sid"] for d in sorted_docs})
    link_brain_dir = bridge_ide_and_cli_brain_sessions(brain_dir, all_sids)

    for doc in sorted_docs:
        raw_txt = doc["path"].read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
        orig_sid = doc["origin_sid"]
        orig_bdir = brain_dir / orig_sid
        if orig_bdir.exists():
            for img_name, src_img in canonical_images.items():
                dst_img = orig_bdir / img_name
                if src_img.resolve() != dst_img.resolve():
                    shutil.copy2(src_img, dst_img)
            orig_md = orig_bdir / doc["name"]
            rewritten_orig = rewrite_md_images_for_brain_dir(raw_txt, orig_bdir)
            _write_text_preserving_mtime(orig_md, rewritten_orig, doc["mtime"])
            doc_iso = dt.datetime.fromtimestamp(doc["mtime"], tz=dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f0Z"
            )
            write_artifact_metadata(orig_md, doc["purpose"], orig_sid, updated_at_iso=doc_iso)
            doc["brain_path"] = orig_md

    generated_hubs: list[Path] = []
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sessions_by_start = sorted(sessions, key=lambda s: (s["first_step"], s["first_ts_iso"]))
    session_num_map = {s["id"]: i + 1 for i, s in enumerate(sessions_by_start)}

    for sid in target_session_ids:
        tdir = brain_dir / sid
        if not tdir.exists():
            continue

        for doc in sorted_docs:
            if doc["origin_sid"] != sid and doc.get("brain_path") and Path(doc["brain_path"]).exists():
                stale_md = tdir / doc["name"]
                stale_meta = tdir / f"{doc['name']}.metadata.json"
                if stale_md.exists() and stale_meta.exists():
                    try:
                        mobj = json.loads(stale_meta.read_text(encoding="utf-8", errors="ignore"))
                        if mobj.get("originSession") == doc["origin_sid"]:
                            stale_md.unlink(missing_ok=True)
                            stale_meta.unlink(missing_ok=True)
                    except Exception:
                        pass

        hub_lines = [
            f"# ⚡ `{workspace.name}` — Multi-Session & Fork Command Center",
            "",
            "> [!TIP]",
            f"> **Zero-Context-Overhead Sync:** All {len(sorted_docs)} project guides and {len(sessions)} session/fork logs are indexed in this session's native artifact hub (`{sid}`) by an external Python script (`0` LLM tokens used). Click any document below to open the original brain artifact in **Antigravity's native styled Artifact Viewer**.",
            "",
            "---",
            "",
            f"## 1. Synced Project Knowledge Base ({len(sorted_docs)} Native Artifacts)",
            "",
            "| Category | Timestamp | Document (Click for Native View) | Summary & Purpose | Key Sections | Origin Session (Full ID) |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for doc in sorted_docs:
            md_name = doc["name"]
            cat = doc["category"]
            purpose = doc["purpose"]
            st = doc["stats"]
            h2_badges = " · ".join(f"`{h}`" for h in st["h2s"]) if st["h2s"] else "—"
            vis_str = f" · `{st['visual_count']} visuals`" if st["visual_count"] > 0 else ""
            orig_full = doc["origin_sid"]
            orig_link = f"`{orig_full}` [↗](conversation://{orig_full})"
            scope_col = f"{orig_link} (`{st['line_count']} lines`{vis_str})"
            bridged_candidate = link_brain_dir / orig_full / md_name
            orig_brain_path = (
                bridged_candidate
                if bridged_candidate.exists()
                else (doc.get("brain_path") or (brain_dir / orig_full / md_name))
            )
            orig_brain_norm = str(orig_brain_path).replace("\\", "/").lstrip("/")
            doc_col = f"[**`{md_name}`**](file:///{orig_brain_norm})"
            hub_lines.append(
                f"| **{cat}** | `{doc['updated_str']}` | {doc_col} | {purpose} | {h2_badges} | {scope_col} |"
            )

        root_count = len({s["root_id"] for s in sessions})
        hub_lines.extend(
            [
                "",
                "---",
                "",
                f"## 2. Session & Fork Telemetry ({len(sessions)} Sessions across {root_count} Root Tree{'s' if root_count != 1 else ''})",
                "",
                "| Tree & Fork Lineage | Full Session ID (Click to Open / Copy to Resume) | Context Usage (Active / Peak) | Chats & Steps | Started -> Last Active | Authored Docs |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )

        for s in sessions:
            s_id = s["id"]
            t_num = s.get("tree_num", 1)
            f_depth = s.get("fork_depth", 0)
            title_tag = f" *({s['title']})*" if s.get("title") else ""
            is_cur = " **(CURRENT)**" if s_id == sid else ""
            if s.get("is_subagent"):
                agent_lbl = s.get("agent_name") or "subagent"
                at_step = f" @ `step {s['fork_step']}`" if s.get("fork_step") is not None else ""
                lineage = (
                    f"`Tree #{t_num}` · 🤖 **Subagent (`{agent_lbl}`, d={f_depth})** of "
                    f"`{s['parent_id'][:8]}`{at_step}{title_tag}{is_cur}"
                )
            elif s["parent_id"]:
                lineage = (
                    f"`Tree #{t_num}` · 🔀 **Fork (d={f_depth})** of `{s['parent_id'][:8]}` "
                    f"@ `step {s['fork_step']}`{title_tag}{is_cur}"
                )
            else:
                lineage = f"`Tree #{t_num}` · 🌱 **Root Session** (`step 0`){title_tag}{is_cur}"

            id_cell = f"`{s_id}` · [↗ Open](conversation://{s_id})"
            cur_ctx = format_tokens(s["current_ctx_tokens"])
            peak_ctx = format_tokens(s["peak_ctx_tokens"])
            out_tok = format_tokens(s["total_output_tokens"])
            compact_note = f" (`{s['compaction_count']}x compacted`)" if s["compaction_count"] > 0 else ""
            ctx_cell = f"**`{cur_ctx}`** active / `{peak_ctx}` peak{compact_note} · `{out_tok}` out"

            step_span = s["last_step"] - s["first_step"] + 1
            chats_cell = f"**`{s['user_chats']} chats`** · `{step_span} steps` (`#{s['first_step']}..#{s['last_step']}`)"
            time_cell = f"`{s['started_local']}` -> `{s['last_active']}`"

            valid_authored = [a for a in (s.get("authored_docs") or []) if a in canonical_mds]
            doc_links: list[str] = []
            for a in valid_authored:
                orig_sid_a = canonical_mds[a]["origin_sid"]
                bridged_art = link_brain_dir / orig_sid_a / a
                s_art_path = s["path"] / a
                if bridged_art.exists():
                    target_art = bridged_art
                elif s_art_path.exists():
                    target_art = s_art_path
                else:
                    target_art = canonical_mds[a].get("brain_path") or (brain_dir / orig_sid_a / a)
                target_norm = str(target_art).replace("\\", "/").lstrip("/")
                doc_links.append(f"[`{a}`](file:///{target_norm})")
            docs_cell = " · ".join(doc_links) if doc_links else "—"
            hub_lines.append(
                f"| {lineage} | {id_cell} | {ctx_cell} | {chats_cell} | {time_cell} | {docs_cell} |"
            )

        hub_lines.extend(
            [
                "",
                "### Multi-Root Session Fork Forest (`mermaid`)",
                "",
                "```mermaid",
                "flowchart LR",
            ]
        )
        trees: dict[int, list[dict[str, Any]]] = {}
        for s in sessions_by_start:
            t_num = s.get("tree_num", 1)
            trees.setdefault(t_num, []).append(s)

        for t_num in sorted(trees.keys()):
            tree_sessions = trees[t_num]
            root_sess = next((x for x in tree_sessions if not x["parent_id"]), tree_sessions[0])
            r_short = root_sess["id"][:8]
            r_title = f" - {root_sess['title']}" if root_sess.get("title") else ""
            hub_lines.append(f'    subgraph T{t_num}["Tree #{t_num} (Root: {r_short}{r_title})"]')
            for s in tree_sessions:
                num = session_num_map[s["id"]]
                s_short = s["id"][:8]
                cur_tag = " [CURRENT]" if s["id"] == sid else ""
                ctx_lbl = format_tokens(s["current_ctx_tokens"])
                peak_lbl = format_tokens(s["peak_ctx_tokens"])
                f_depth = s.get("fork_depth", 0)
                if s.get("is_subagent"):
                    agent_lbl = s.get("agent_name") or "subagent"
                    role_lbl = f"Subagent {agent_lbl}"
                elif s["parent_id"]:
                    role_lbl = f"Fork d={f_depth} @{s['fork_step']}"
                else:
                    role_lbl = "Root"
                u_chats = s["user_chats"]
                f_step = s["first_step"]
                l_step = s["last_step"]
                hub_lines.append(
                    f'        N{num}["S{num}: {s_short}{cur_tag} ({role_lbl}) | {u_chats} chats, steps {f_step}..{l_step} | Ctx: {ctx_lbl} (peak {peak_lbl})"]'
                )
            for s in tree_sessions:
                num = session_num_map[s["id"]]
                if s["parent_id"] and s["parent_id"] in session_num_map:
                    pnum = session_num_map[s["parent_id"]]
                    fk_step = s["fork_step"]
                    if s.get("is_subagent"):
                        agent_lbl = s.get("agent_name") or "subagent"
                        edge_lbl = f"subagent ({agent_lbl})" + (f" @ step {fk_step}" if fk_step is not None else "")
                    else:
                        edge_lbl = f"forked @ step {fk_step}"
                    hub_lines.append(f'        N{pnum} -- "{edge_lbl}" --> N{num}')
            hub_lines.append("    end")

        hub_lines.extend(
            [
                "```",
                "",
                "---",
                "",
                "## 3. Recent Prompts Per Session / Fork",
                "",
            ]
        )
        for s in sessions:
            s_id = s["id"]
            is_cur_badge = " *(Current Session)*" if s_id == sid else ""
            if s.get("is_subagent"):
                agent_lbl = s.get("agent_name") or "subagent"
                role_badge = f"Subagent (`{agent_lbl}`) of `{s['parent_id']}`" + (
                    f" @ step `{s['fork_step']}`" if s.get("fork_step") is not None else ""
                )
            elif s["parent_id"]:
                role_badge = f"Fork of `{s['parent_id']}` @ step `{s['fork_step']}`"
            else:
                role_badge = "Root Session (`step 0`)"
            hub_lines.append(
                f"### `{s_id}` · [↗ Open](conversation://{s_id}){is_cur_badge}"
            )
            hub_lines.append(
                f"- **Lineage:** {role_badge} · **Context:** `{format_tokens(s['current_ctx_tokens'])}` active (`{format_tokens(s['peak_ctx_tokens'])}` peak) · **Chats:** `{s['user_chats']}` (`steps #{s['first_step']}..#{s['last_step']}`) · **Active:** `{s['started_local']}` -> `{s['last_active']}`"
            )
            if s["prompts"]:
                for pr in s["prompts"][-5:]:
                    one_line = " ".join(pr["text"].splitlines())
                    hub_lines.append(f"  - **`[{pr['timestamp']} · step #{pr['step']}]`** {one_line}")
            hub_lines.append("")

        hub_lines.extend(
            [
                "---",
                "",
                "## 4. Git Branches & Tip Commits",
                "",
                "| Branch | Tip Commit | Subject |",
                "| :--- | :--- | :--- |",
            ]
        )
        for b in git_state["branches"]:
            marker = " **(active)**" if b["name"] == git_state["current_branch"] else ""
            hub_lines.append(f"| `{b['name']}`{marker} | `{b['sha']}` | {b['subject']} |")

        hub_lines.extend(
            [
                "",
                f"*Last synced by `local-recap` skill at `{now_str}`.*",
                "",
            ]
        )

        hub_path = tdir / "PROJECT_HUB.md"
        hub_path.write_text("\n".join(hub_lines), encoding="utf-8", newline="\n")
        write_artifact_metadata(
            hub_path,
            f"Unified Native Antigravity Command Center for {workspace.name} ({len(sorted_docs)} synced artifacts, fork tree, and session telemetry across {len(sessions)} sessions).",
            sid,
        )
        generated_hubs.append(hub_path)

    return generated_hubs
