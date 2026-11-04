"""Markdown renderer and brain-hub writer for `PROJECT_HUB.md`."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path

from .artifact_sync import (
    _write_text_preserving_mtime,
    bridge_ide_and_cli_brain_sessions,
    collect_hot_files,
    collect_rich_media,
    rewrite_md_images_for_brain_dir,
    sort_canonical_docs,
    write_artifact_metadata,
)
from .models import (
    ArtifactDoc,
    GitState,
    RichMediaItem,
    SessionInfo,
    TouchEvent,
    file_url,
    format_size,
    format_tokens,
)


def _sanitize_mermaid_label(text: str, max_len: int = 34) -> str:
    """Clean and truncate arbitrary text so it is safe inside a Mermaid double-quoted label."""
    cleaned = re.sub(r'["\'`\[\](){}<>#;&|]+', " ", text or "")
    cleaned = " ".join(cleaned.split())
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[: max_len - 1].rsplit(" ", 1)[0]
    return (cut if len(cut) >= max_len // 2 else cleaned[: max_len - 1]) + "…"


def format_context_meter(s: SessionInfo) -> str:
    """Format a 10-block visual context progress bar supporting both 256k and 1M context windows."""
    cur_tok = s.current_ctx_tokens
    peak_tok = s.peak_ctx_tokens
    compacts = s.compaction_count
    pct_1m = min(100, round(cur_tok / 1_000_000 * 100))
    pct_256k = min(100, round(cur_tok / 256_000 * 100))
    compact_str = f" · `{compacts}x compacted`" if compacts > 0 else ""

    if peak_tok > 270_000:
        filled = max(1 if cur_tok > 0 else 0, min(10, round(pct_1m / 10)))
        bar = "▰" * filled + "▱" * (10 - filled)
        dot = "🟠" if pct_1m >= 80 else ("🟡" if pct_1m >= 50 else "🟢")
        advice = (
            "Approaching 1M context limit — consider `/compact` or fork"
            if pct_1m >= 80
            else "1M context window active"
        )
        return (
            f"{dot} `{bar}` **`{format_tokens(cur_tok)}`** active / `{format_tokens(peak_tok)}` peak "
            f"(`{pct_1m}%` of `1M` window{compact_str}) — *{advice}*"
        )

    filled = max(1 if cur_tok > 0 else 0, min(10, round(pct_256k / 10)))
    bar = "▰" * filled + "▱" * (10 - filled)
    if cur_tok >= 185_000:
        dot = "🟠"
        advice = (
            "Near 256k auto-compact ceiling (good checkpoint to `/compact` or fork on 256k tier; "
            f"only `{pct_1m}%` used if on a 1M model)"
        )
    elif cur_tok >= 100_000:
        dot = "🟡"
        advice = f"Moderate context load (`{pct_256k}%` of 256k / `{pct_1m}%` of 1M)"
    else:
        dot = "🟢"
        advice = f"Fresh context headroom (`{pct_256k}%` of 256k / `{pct_1m}%` of 1M)"
    return (
        f"{dot} `{bar}` **`{format_tokens(cur_tok)}`** active / `{format_tokens(peak_tok)}` peak "
        f"(`{pct_256k}%` of `256k` compact · `{pct_1m}%` of `1M` max{compact_str}) — *{advice}*"
    )


def render_project_hub(
    sid: str,
    workspace: Path,
    brain_dir: Path,
    link_brain_dir: Path,
    sorted_docs: list[ArtifactDoc],
    canonical_mds: dict[str, ArtifactDoc],
    sessions: list[SessionInfo],
    git_state: GitState,
    hot_files: list[TouchEvent],
    rich_media_list: list[RichMediaItem],
    now_str: str,
) -> str:
    """Render the complete `PROJECT_HUB.md` Markdown document for session `sid`."""
    primary_sessions = [s for s in sessions if not s.is_subagent]
    subagent_sessions = [s for s in sessions if s.is_subagent]
    if not primary_sessions:
        primary_sessions = list(sessions)
        subagent_sessions = []

    subagents_by_parent: dict[str, list[SessionInfo]] = {}
    for sub in subagent_sessions:
        pid = sub.parent_id or ""
        subagents_by_parent.setdefault(pid, []).append(sub)

    primary_by_start = sorted(primary_sessions, key=lambda s: (s.first_step, s.first_ts_iso))
    session_num_map = {s.id: i + 1 for i, s in enumerate(primary_by_start)}
    sess_lookup = {s.id: s for s in sessions}

    total_doc_lines = sum(d.stats.line_count for d in sorted_docs)
    total_doc_visuals = sum(d.stats.visual_count for d in sorted_docs)
    root_count = len({s.root_id for s in primary_sessions})
    fork_count = sum(1 for s in primary_sessions if s.parent_id)
    total_chats = sum(s.user_chats for s in primary_sessions)
    total_steps = sum(max(0, s.last_step - s.first_step + 1) for s in sessions)
    total_output_tok = sum(s.total_output_tokens for s in sessions)

    cur_sess = sess_lookup.get(sid) or (primary_sessions[0] if primary_sessions else None)
    wt = git_state.working_tree
    cur_branch = git_state.current_branch or "detached"
    active_branch_obj = next(
        (b for b in git_state.branches if b.name == cur_branch),
        git_state.branches[0] if git_state.branches else None,
    )
    tip_sha = f" (`{active_branch_obj.sha}`)" if active_branch_obj else ""
    total_dirty = wt.modified + wt.added + wt.deleted + wt.untracked
    wt_short_badge = "🟢 Clean" if wt.clean else f"🟡 {total_dirty} uncommitted"
    media_badge = f" · `{len(rich_media_list)} HTML/PDF`" if rich_media_list else ""

    if not git_state.branches and wt.clean:
        wt_line = "⚪ Not a Git repository (or no commits yet)"
    elif wt.clean:
        wt_line = f"🟢 Clean working tree on `{cur_branch}`{tip_sha}"
    else:
        dirty_parts: list[str] = []
        if wt.modified:
            dirty_parts.append(f"`{wt.modified} modified`")
        if wt.added:
            dirty_parts.append(f"`{wt.added} staged`")
        if wt.deleted:
            dirty_parts.append(f"`{wt.deleted} deleted`")
        if wt.untracked:
            dirty_parts.append(f"`{wt.untracked} untracked`")
        ins_del = ""
        if wt.insertions or wt.deletions:
            ins_del = f" · `+{wt.insertions} / -{wt.deletions} lines`"
        file_pills: list[str] = []
        for fitem in wt.files[:6]:
            f_badge = fitem.badge or "modified"
            if (workspace / fitem.rel).exists():
                file_pills.append(f"[`{fitem.rel}`]({file_url(fitem.abs)}) (`{f_badge}`)")
            else:
                file_pills.append(f"`{fitem.rel}` (`{f_badge}`)")
        more_files = f" *(+{len(wt.files) - 6} more)*" if len(wt.files) > 6 else ""
        files_suffix = f" — {' · '.join(file_pills)}{more_files}" if file_pills else ""
        wt_line = f"🟡 **Dirty ({', '.join(dirty_parts)}{ins_del})**{files_suffix}"

    if hot_files:
        hot_pills = [
            f"[`{hf.rel}`]({file_url(hf.abs)}) (`{hf.ts_local}` · `{hf.session_id[:8]}`)"
            for hf in hot_files
        ]
        hot_files_line = " · ".join(hot_pills)
    else:
        hot_files_line = "*(No workspace source code edits recorded in session transcripts yet)*"

    latest_doc_line = "—"
    if sorted_docs:
        ld = sorted_docs[0]
        ld_bridged = link_brain_dir / ld.origin_sid / ld.name
        ld_path = (
            ld_bridged
            if ld_bridged.exists()
            else (ld.brain_path or (brain_dir / ld.origin_sid / ld.name))
        )
        latest_doc_line = (
            f"[**`{ld.name}`**]({file_url(ld_path)}) "
            f"(`{ld.updated_str}` · `{ld.stats.line_count} lines` · `{ld.origin_sid[:8]}`)"
        )

    latest_prompt_entry: tuple[str, str, str, int] | None = None
    for s in primary_sessions:
        if s.prompts:
            lp = s.prompts[-1]
            cand = (lp.timestamp, s.id, " ".join(lp.text.splitlines()), lp.step)
            if latest_prompt_entry is None or cand[0] >= latest_prompt_entry[0]:
                latest_prompt_entry = cand

    if cur_sess:
        c_tnum = cur_sess.tree_num
        c_title = f" *({cur_sess.title})*" if cur_sess.title else ""
        if cur_sess.parent_id:
            c_role = f"🔀 Fork (d={cur_sess.fork_depth}) of `{cur_sess.parent_id[:8]}` @ `step {cur_sess.fork_step}`"
        else:
            c_role = "🌱 Root Session (`step 0`)"
        active_sess_line = (
            f"`{cur_sess.id}` — `Tree #{c_tnum}` · {c_role}{c_title} · *Synced `{now_str}` (`0` LLM tokens)*"
        )
        ctx_meter_line = format_context_meter(cur_sess)
    else:
        active_sess_line = f"`{sid}` · *Synced `{now_str}` (`0` LLM tokens)*"
        ctx_meter_line = "—"

    hub_lines = [
        f"# ⚡ `{workspace.name}` — Multi-Session & Fork Command Center",
        "",
        "| 📚 Knowledge Base | 🌱 Primary Sessions | 🤖 Subagents | 💬 Prompt Turns | 🧠 Cumulative Output | 🌿 Active Git Branch |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
        (
            f"| **`{len(sorted_docs)} docs`** (`{total_doc_lines:,} lines` · `{total_doc_visuals} visuals`{media_badge}) "
            f"| **`{len(primary_sessions)}`** (`{root_count} root` · `{fork_count} fork{'s' if fork_count != 1 else ''}`) "
            f"| **`{len(subagent_sessions)}`** background run{'s' if len(subagent_sessions) != 1 else ''} "
            f"| **`{total_chats} chats`** (`{total_steps:,} steps`) "
            f"| **`{format_tokens(total_output_tok)}`** generated "
            f"| `{cur_branch}`{tip_sha} · {wt_short_badge} |"
        ),
        "",
        "> [!NOTE]",
        f"> - **Active Session:** {active_sess_line}",
        f"> - **Context Meter (`256k` / `1M`):** {ctx_meter_line}",
        f"> - **Working Tree:** {wt_line}",
        f"> - **Recently Touched Code:** {hot_files_line}",
        f"> - **Latest Updated Guide:** {latest_doc_line}",
    ]
    if latest_prompt_entry is not None:
        lp_ts, lp_sid, lp_txt, lp_step = latest_prompt_entry
        hub_lines.append(
            f"> - **Latest Prompt (`{lp_ts}` · `{lp_sid[:8]}` · `step #{lp_step}`):** *{lp_txt}*"
        )

    hub_lines.extend(
        [
            "",
            "---",
            "",
            f"## 1. Synced Project Knowledge Base ({len(sorted_docs)} Native Artifacts)",
            "",
            "| Category | Timestamp | Document (Click for Native View) | Summary & Purpose | Key Sections | Origin Session (Full ID) |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )

    for doc in sorted_docs:
        st = doc.stats
        h2_badges = " · ".join(f"`{h}`" for h in st.h2s) if st.h2s else "—"
        vis_str = f" · `{st.visual_count} visuals`" if st.visual_count > 0 else ""
        scope_col = f"`{doc.origin_sid}` (`{st.line_count} lines`{vis_str})"
        bridged_candidate = link_brain_dir / doc.origin_sid / doc.name
        orig_brain_path = (
            bridged_candidate
            if bridged_candidate.exists()
            else (doc.brain_path or (brain_dir / doc.origin_sid / doc.name))
        )
        doc_col = f"[**`{doc.name}`**]({file_url(orig_brain_path)})"
        hub_lines.append(
            f"| **{doc.category}** | `{doc.updated_str}` | {doc_col} | {doc.purpose} | {h2_badges} | {scope_col} |"
        )

    if rich_media_list:
        hub_lines.extend(
            [
                "",
                f"### 🎨 Interactive HTML Apps & PDF Exports ({len(rich_media_list)} File{'s' if len(rich_media_list) != 1 else ''})",
                "",
                "| Type | Updated | File (Click to Open) | Workspace / Brain Path | Size |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ]
        )
        for m in rich_media_list:
            m_type = "🌐 **Interactive HTML**" if m.ext == ".html" else "📄 **PDF Document**"
            m_ts = dt.datetime.fromtimestamp(m.mtime).strftime("%Y-%m-%d %H:%M")
            m_link = f"[**`{m.name}`**]({file_url(m.path)})"
            m_sz = format_size(m.size_bytes)
            hub_lines.append(f"| {m_type} | `{m_ts}` | {m_link} | `{m.rel_label}` | `{m_sz}` |")

    sub_header_suffix = (
        f" · {len(subagent_sessions)} Subagent Run{'s' if len(subagent_sessions) != 1 else ''}"
        if subagent_sessions
        else ""
    )
    hub_lines.extend(
        [
            "",
            "---",
            "",
            f"## 2. Session & Fork Telemetry ({len(primary_sessions)} Primary Session{'s' if len(primary_sessions) != 1 else ''} across {root_count} Root Tree{'s' if root_count != 1 else ''}{sub_header_suffix})",
            "",
            "| Tree & Fork Lineage | Full Session ID (Copy to Resume) | Context Usage (Active / Peak) | Chats & Steps | Started -> Last Active | Authored Docs |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )

    def _render_session_row(s: SessionInfo) -> str:
        s_id = s.id
        t_num = s.tree_num
        f_depth = s.fork_depth
        title_tag = f" *({s.title})*" if s.title else ""
        is_cur = " **(CURRENT)**" if s_id == sid else ""
        if s.is_subagent:
            agent_lbl = s.agent_name or "subagent"
            at_step = f" @ `step {s.fork_step}`" if s.fork_step is not None else ""
            p_short = (s.parent_id or "")[:8]
            lineage = (
                f"`Tree #{t_num}` · 🤖 **Subagent (`{agent_lbl}`, d={f_depth})** of "
                f"`{p_short}`{at_step}{title_tag}{is_cur}"
            )
        elif s.parent_id:
            lineage = (
                f"`Tree #{t_num}` · 🔀 **Fork (d={f_depth})** of `{s.parent_id[:8]}` "
                f"@ `step {s.fork_step}`{title_tag}{is_cur}"
            )
        else:
            lineage = f"`Tree #{t_num}` · 🌱 **Root Session** (`step 0`){title_tag}{is_cur}"

        id_cell = f"`{s_id}`"
        cur_ctx = format_tokens(s.current_ctx_tokens)
        peak_ctx = format_tokens(s.peak_ctx_tokens)
        out_tok = format_tokens(s.total_output_tokens)
        if s.compaction_count > 0:
            if s.inherited_compactions > 0:
                compact_note = f" (`{s.compaction_count}x compacted`, `{s.inherited_compactions}x` inherited)"
            else:
                compact_note = f" (`{s.compaction_count}x compacted`)"
        else:
            compact_note = ""
        ctx_cell = f"**`{cur_ctx}`** active / `{peak_ctx}` peak{compact_note} · `{out_tok}` out"

        step_span = s.last_step - s.first_step + 1
        child_subs = subagents_by_parent.get(s_id, [])
        sub_badge = (
            f" · 🤖 `{len(child_subs)} subagent{'s' if len(child_subs) != 1 else ''}`"
            if child_subs
            else ""
        )
        if s.parent_id and not s.is_subagent and s.inherited_chats > 0:
            tot_c = s.user_chats + s.inherited_chats
            chats_cell = (
                f"**`+{s.user_chats} chats`** (`{tot_c} total`) · `+{step_span} steps` "
                f"(`#{s.first_step}..#{s.last_step}`){sub_badge}"
            )
        else:
            chats_cell = (
                f"**`{s.user_chats} chats`** · `{step_span} steps` "
                f"(`#{s.first_step}..#{s.last_step}`){sub_badge}"
            )
        time_cell = f"`{s.started_local}` -> `{s.last_active}`"

        valid_authored = [a for a in (s.authored_docs or []) if a in canonical_mds]
        doc_links: list[str] = []
        for a in valid_authored:
            orig_sid_a = canonical_mds[a].origin_sid
            bridged_art = link_brain_dir / orig_sid_a / a
            s_art_path = s.path / a
            if bridged_art.exists():
                target_art = bridged_art
            elif s_art_path.exists():
                target_art = s_art_path
            else:
                target_art = canonical_mds[a].brain_path or (brain_dir / orig_sid_a / a)
            doc_links.append(f"[`{a}`]({file_url(target_art)})")
        docs_cell = " · ".join(doc_links) if doc_links else "—"
        return f"| {lineage} | {id_cell} | {ctx_cell} | {chats_cell} | {time_cell} | {docs_cell} |"

    for s in primary_sessions:
        hub_lines.append(_render_session_row(s))

    if subagent_sessions:
        hub_lines.extend(
            [
                "",
                "<details>",
                f"<summary>🤖 <strong>Subagent Tracking ({len(subagent_sessions)} background run{'s' if len(subagent_sessions) != 1 else ''})</strong> — Click to expand telemetry</summary>",
                "",
                "| Tree & Parent Lineage | Subagent Session ID | Context Usage (Active / Peak) | Chats & Steps | Started -> Last Active | Authored Docs |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )
        for sub_s in subagent_sessions:
            hub_lines.append(_render_session_row(sub_s))
        hub_lines.extend(["", "</details>"])

    hub_lines.extend(
        [
            "",
            "### 🗺️ Multi-Root Session & Fork Lineage (`mermaid`)",
            "",
            "```mermaid",
            "%%{init: {'flowchart': {'curve': 'basis', 'padding': 16, 'nodeSpacing': 52, 'rankSpacing': 64, 'wrappingWidth': 340}}}%%",
            "flowchart TD",
            "    classDef wsHub fill:#10b98122,stroke:#10b981,stroke-width:2px,rx:10,ry:10",
            "    classDef sessCurrent fill:#3b82f624,stroke:#3b82f6,stroke-width:2.5px,rx:10,ry:10",
            "    classDef sessHot fill:#f59e0b24,stroke:#f59e0b,stroke-width:2px,rx:10,ry:10",
            "    classDef sessRoot fill:#64748b22,stroke:#64748b,stroke-width:1.5px,rx:10,ry:10",
            "    classDef sessFork fill:#a855f724,stroke:#a855f7,stroke-width:2px,rx:10,ry:10",
            "    classDef subNode fill:#06b6d422,stroke:#06b6d4,stroke-width:1.5px,stroke-dasharray: 4 3,rx:10,ry:10",
        ]
    )

    pad = "\u00a0\u00a0"
    ws_title = _sanitize_mermaid_label(workspace.name, 28)
    branch_title = _sanitize_mermaid_label(cur_branch, 20)
    ws_line1 = f"{pad}<b>⚡ {ws_title}</b> · 🌿 {branch_title}{pad}"
    ws_line2 = (
        f"{pad}{len(primary_sessions)} session{'s' if len(primary_sessions) != 1 else ''} ({root_count} tree{'s' if root_count != 1 else ''}"
        + (f", {fork_count} fork{'s' if fork_count != 1 else ''}" if fork_count else "")
        + (f", {len(subagent_sessions)} subagent{'s' if len(subagent_sessions) != 1 else ''}" if subagent_sessions else "")
        + f") · 💬 {total_chats} chats · 🧠 {format_tokens(total_output_tok)} out{pad}"
    )
    hub_lines.append(f'    WS("{ws_line1}<br/>{ws_line2}")')
    hub_lines.append("    class WS wsHub")

    trees: dict[int, list[SessionInfo]] = {}
    for s in primary_by_start:
        trees.setdefault(s.tree_num, []).append(s)

    sorted_tnums = sorted(trees.keys())
    tree_root_node: dict[int, str] = {}
    tree_bottom_node: dict[int, str] = {}

    for t_num in sorted_tnums:
        tree_sessions = trees[t_num]
        root_sess = next((x for x in tree_sessions if not x.parent_id), tree_sessions[0])
        root_node_id = f"N{session_num_map[root_sess.id]}"
        tree_root_node[t_num] = root_node_id
        bottom_candidate = root_node_id
        best_depth = -1

        for s in tree_sessions:
            num = session_num_map[s.id]
            node_id = f"N{num}"
            s_short = s.id[:8]
            ctx_lbl = format_tokens(s.current_ctx_tokens)
            peak_lbl = format_tokens(s.peak_ctx_tokens)
            is_cur = s.id == sid

            if s.peak_ctx_tokens > 270_000:
                pct_1m = min(100, round(s.current_ctx_tokens / 1_000_000 * 100))
                ctx_dot = "🟠" if pct_1m >= 80 else ("🟡" if pct_1m >= 50 else "🟢")
                is_hot = pct_1m >= 80
            else:
                ctx_dot = "🟠" if s.current_ctx_tokens >= 185_000 else ("🟡" if s.current_ctx_tokens >= 100_000 else "🟢")
                is_hot = s.current_ctx_tokens >= 185_000

            fork_at = f" @ {s.fork_step}" if s.fork_step is not None else ""
            if is_cur and s.parent_id:
                header_line = f"<b>⚡ Fork{fork_at} · {s_short} (d={s.fork_depth}) [CURRENT]</b>"
            elif is_cur:
                header_line = f"<b>⚡ Tree #{t_num} · {s_short} [CURRENT]</b>"
            elif s.parent_id:
                header_line = f"<b>🔀 Fork{fork_at} · {s_short} (d={s.fork_depth})</b>"
            else:
                header_line = f"<b>🌱 Tree #{t_num} · {s_short}</b>"

            lines_in_box = [header_line]
            if s.title:
                safe_title = _sanitize_mermaid_label(s.title, max_len=34)
                if safe_title:
                    lines_in_box.append(f"<i>{safe_title}</i>")

            step_span = max(0, s.last_step - s.first_step + 1)
            out_lbl = format_tokens(s.total_output_tokens)
            valid_authored = [a for a in (s.authored_docs or []) if a in canonical_mds]
            doc_badge = f" · 📚 {len(valid_authored)}" if valid_authored else ""
            if s.parent_id and s.inherited_chats > 0:
                tot_c = s.user_chats + s.inherited_chats
                lines_in_box.append(
                    f"💬 +{s.user_chats} chats ({tot_c} tot) · +{step_span} steps · {out_lbl} out{doc_badge}"
                )
            else:
                lines_in_box.append(
                    f"💬 {s.user_chats} chat{'s' if s.user_chats != 1 else ''} · {step_span} steps · {out_lbl} out{doc_badge}"
                )

            if s.compaction_count > 0:
                if s.inherited_compactions > 0:
                    cmp_badge = f" · {s.compaction_count}x cmp ({s.inherited_compactions}x inh)"
                else:
                    cmp_badge = f" · {s.compaction_count}x cmp"
            else:
                cmp_badge = ""
            lines_in_box.append(f"{ctx_dot} Ctx: {ctx_lbl} / {peak_lbl}{cmp_badge}")

            label_str = "<br/>".join(f"{pad}{ln}{pad}" for ln in lines_in_box)
            hub_lines.append(f'    {node_id}("{label_str}")')

            if is_cur:
                node_cls = "sessCurrent"
            elif s.parent_id:
                node_cls = "sessFork"
            elif is_hot:
                node_cls = "sessHot"
            else:
                node_cls = "sessRoot"
            hub_lines.append(f"    class {node_id} {node_cls}")

            if s.fork_depth >= best_depth:
                best_depth = s.fork_depth
                bottom_candidate = node_id

            child_subs = subagents_by_parent.get(s.id, [])
            if child_subs:
                sub_node_id = f"SUB{num}"
                if len(child_subs) == 1:
                    sub0 = child_subs[0]
                    ag_lbl = _sanitize_mermaid_label(sub0.agent_name or "subagent", 14)
                    sub_steps = max(0, sub0.last_step - sub0.first_step + 1)
                    sub_out = format_tokens(sub0.total_output_tokens)
                    sub_ctx = format_tokens(sub0.current_ctx_tokens)
                    sub_at = f" @ {sub0.fork_step}" if sub0.fork_step is not None else ""
                    sub_label = (
                        f"{pad}<b>🤖 {ag_lbl}{sub_at} · {sub0.id[:8]}</b>{pad}<br/>"
                        f"{pad}{sub_steps} steps · Ctx {sub_ctx} · {sub_out} out{pad}"
                    )
                else:
                    ag_types = sorted({_sanitize_mermaid_label(x.agent_name or "subagent", 12) for x in child_subs})
                    types_str = ", ".join(ag_types[:2]) + ("…" if len(ag_types) > 2 else "")
                    tot_sub_steps = sum(max(0, x.last_step - x.first_step + 1) for x in child_subs)
                    tot_sub_out = format_tokens(sum(x.total_output_tokens for x in child_subs))
                    sub_label = (
                        f"{pad}<b>🤖 {len(child_subs)} Subagents ({types_str})</b>{pad}<br/>"
                        f"{pad}{tot_sub_steps} steps total · {tot_sub_out} out{pad}"
                    )
                hub_lines.append(f'    {sub_node_id}("{sub_label}")')
                hub_lines.append(f"    class {sub_node_id} subNode")
                hub_lines.append(f"    {node_id} -.-> {sub_node_id}")
                if s.fork_depth + 1 >= best_depth:
                    best_depth = s.fork_depth + 1
                    bottom_candidate = sub_node_id

        for s in tree_sessions:
            num = session_num_map[s.id]
            if s.parent_id and s.parent_id in session_num_map:
                pnum = session_num_map[s.parent_id]
                hub_lines.append(f"    N{pnum} ==> N{num}")

        tree_bottom_node[t_num] = bottom_candidate

    max_cols = 3
    for idx, t_num in enumerate(sorted_tnums):
        r_node = tree_root_node[t_num]
        if idx < max_cols:
            hub_lines.append(f"    WS --> {r_node}")
        else:
            prev_t_num = sorted_tnums[idx - max_cols]
            prev_bottom = tree_bottom_node[prev_t_num]
            hub_lines.append(f"    {prev_bottom} ~~~ {r_node}")

    hub_lines.extend(
        [
            "```",
            "",
            "<details>",
            "<summary>ℹ️ <strong>Legends & Shorthand</strong> — Click to expand</summary>",
            "",
            "| Card / Shorthand | Meaning |",
            "| :--- | :--- |",
            "| 🟢 **Emerald Border** (`Workspace`) | Project workspace summary (branch, total sessions, chats, output tokens) |",
            "| 🔵 **Blue Border** (`[CURRENT]`) | Active session for this `PROJECT_HUB.md` view |",
            "| ⚪ **Slate Border** (`Tree #N`) | Primary root session (`step 0`) |",
            "| 🟠 **Amber Border** (`≥185k`) | High context load (approaching `256k` compaction ceiling) |",
            "| 🟣 **Purple Border** (`Fork @ step`) | Branched session forked from a parent session at `@ step` |",
            "| 🔹 **Dashed Cyan** (`Subagents`) | Background subagent run(s) spawned by parent session |",
            "| `d=N` | Fork depth from the root session |",
            "| `+N chats (M tot)` | `N` new chats in this fork (`M` cumulative chats including parent history) |",
            "| `out` | Cumulative output tokens generated by the session |",
            "| `📚 N` | Number of generated notes authored in the session |",
            "| `Ctx: active / peak` | Current context tokens vs. highest context tokens reached in trajectory |",
            "| `Nx cmp` | Total number of context window compactions (`N`) |",
            "| `Mx inh` | Number of compactions (`M`) inherited from parent before the fork step |",
            "",
            "</details>",
            "",
            "---",
            "",
            "## 3. Recent Prompts Per Session / Fork",
            "",
        ]
    )

    def _append_session_prompts(s: SessionInfo) -> None:
        s_id = s.id
        is_cur_badge = " *(Current Session)*" if s_id == sid else ""
        if s.is_subagent:
            agent_lbl = s.agent_name or "subagent"
            role_badge = f"Subagent (`{agent_lbl}`) of `{s.parent_id}`" + (
                f" @ step `{s.fork_step}`" if s.fork_step is not None else ""
            )
        elif s.parent_id:
            role_badge = f"Fork of `{s.parent_id}` @ step `{s.fork_step}`"
        else:
            role_badge = "Root Session (`step 0`)"
        hub_lines.append(f"### `{s_id}`{is_cur_badge}")
        hub_lines.append(
            f"- **Lineage:** {role_badge} · **Context:** `{format_tokens(s.current_ctx_tokens)}` active (`{format_tokens(s.peak_ctx_tokens)}` peak) · **Chats:** `{s.user_chats}` (`steps #{s.first_step}..#{s.last_step}`) · **Active:** `{s.started_local}` -> `{s.last_active}`"
        )
        if s.prompts:
            for pr in s.prompts[-5:]:
                one_line = " ".join(pr.text.splitlines())
                hub_lines.append(f"  - **`[{pr.timestamp} · step #{pr.step}]`** {one_line}")
        hub_lines.append("")

    for s in primary_sessions:
        _append_session_prompts(s)

    subagents_with_prompts = [sub_s for sub_s in subagent_sessions if sub_s.prompts]
    if subagents_with_prompts:
        hub_lines.extend(
            [
                "<details>",
                f"<summary>🤖 <strong>Subagent Task Prompts ({len(subagents_with_prompts)} background run{'s' if len(subagents_with_prompts) != 1 else ''})</strong> — Click to expand</summary>",
                "",
            ]
        )
        for sub_s in subagents_with_prompts:
            _append_session_prompts(sub_s)
        hub_lines.extend(["</details>", ""])

    hub_lines.extend(
        [
            "---",
            "",
            "## 4. Git Branches, Working Tree & Recent Commits",
            "",
            "| Branch | Tip Commit | Subject |",
            "| :--- | :--- | :--- |",
        ]
    )
    for b in git_state.branches:
        marker = " **(active)**" if b.name == git_state.current_branch else ""
        hub_lines.append(f"| `{b.name}`{marker} | `{b.sha}` | {b.subject} |")

    if git_state.commits:
        hub_lines.extend(
            [
                "",
                f"### Recent Commits on `{cur_branch}` (Last {len(git_state.commits)})",
                "",
                "| Timestamp | Commit | Refs | Subject |",
                "| :--- | :--- | :--- | :--- |",
            ]
        )
        for c in git_state.commits:
            refs_cell = f"`{c.refs}`" if c.refs else "—"
            hub_lines.append(f"| `{c.date}` | `{c.sha}` | {refs_cell} | {c.subject} |")

    hub_lines.extend(
        [
            "",
            f"*Last synced by `agy-project-hub` skill at `{now_str}`.*",
            "",
        ]
    )
    return "\n".join(hub_lines)


def sync_all_targets(
    sessions: list[SessionInfo],
    canonical_images: dict[str, Path],
    canonical_mds: dict[str, ArtifactDoc],
    workspace: Path,
    git_state: GitState,
    target_session_ids: list[str],
    brain_dir: Path,
) -> list[Path]:
    """Ensure canonical artifacts exist in their origin `brain/<id>/` folder and generate `PROJECT_HUB.md`."""
    sorted_docs = sort_canonical_docs(canonical_mds)
    all_sids = list({s.id for s in sessions} | set(target_session_ids) | {d.origin_sid for d in sorted_docs})
    link_brain_dir = bridge_ide_and_cli_brain_sessions(brain_dir, all_sids)

    for doc in sorted_docs:
        raw_txt = doc.path.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
        orig_sid = doc.origin_sid
        orig_bdir = brain_dir / orig_sid
        if orig_bdir.exists():
            for img_name, src_img in canonical_images.items():
                dst_img = orig_bdir / img_name
                if src_img.resolve() != dst_img.resolve():
                    need_copy = True
                    if dst_img.exists():
                        try:
                            s_st = src_img.stat()
                            d_st = dst_img.stat()
                            if s_st.st_size == d_st.st_size and abs(s_st.st_mtime - d_st.st_mtime) <= 1.0:
                                need_copy = False
                        except Exception:
                            pass
                    if need_copy:
                        shutil.copy2(src_img, dst_img)
            orig_md = orig_bdir / doc.name
            rewritten_orig = rewrite_md_images_for_brain_dir(raw_txt, orig_bdir)
            _write_text_preserving_mtime(orig_md, rewritten_orig, doc.mtime)
            doc_iso = dt.datetime.fromtimestamp(doc.mtime, tz=dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f0Z"
            )
            write_artifact_metadata(orig_md, doc.purpose, orig_sid, updated_at_iso=doc_iso)
            doc.brain_path = orig_md

    generated_hubs: list[Path] = []
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hot_files = collect_hot_files(sessions, workspace, limit=5)
    rich_media_list = collect_rich_media(sessions, workspace)

    for sid in target_session_ids:
        tdir = brain_dir / sid
        if not tdir.exists():
            continue

        # Remove stale duplicate copies of other sessions' artifacts that were synced into `tdir` previously
        for doc in sorted_docs:
            if doc.origin_sid != sid and doc.brain_path and Path(doc.brain_path).exists():
                stale_md = tdir / doc.name
                stale_meta = tdir / f"{doc.name}.metadata.json"
                if stale_md.exists() and stale_meta.exists():
                    try:
                        mobj = json.loads(stale_meta.read_text(encoding="utf-8", errors="ignore"))
                        if mobj.get("originSession") == doc.origin_sid:
                            stale_md.unlink(missing_ok=True)
                            stale_meta.unlink(missing_ok=True)
                    except Exception:
                        pass

        hub_text = render_project_hub(
            sid=sid,
            workspace=workspace,
            brain_dir=brain_dir,
            link_brain_dir=link_brain_dir,
            sorted_docs=sorted_docs,
            canonical_mds=canonical_mds,
            sessions=sessions,
            git_state=git_state,
            hot_files=hot_files,
            rich_media_list=rich_media_list,
            now_str=now_str,
        )
        hub_path = tdir / "PROJECT_HUB.md"
        should_write_hub = True
        if hub_path.exists():
            try:
                old_hub = hub_path.read_text(encoding="utf-8", errors="ignore")
                ts_re = re.compile(r"\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\b")
                if ts_re.sub("<TS>", old_hub).strip() == ts_re.sub("<TS>", hub_text).strip():
                    should_write_hub = False
            except Exception:
                pass
        if should_write_hub:
            hub_path.write_text(hub_text, encoding="utf-8", newline="\n")
            write_artifact_metadata(
                hub_path,
                f"Unified Native Antigravity Command Center for {workspace.name} ({len(sorted_docs)} synced artifacts, fork tree, and session telemetry across {len(sessions)} sessions).",
                sid,
            )
        generated_hubs.append(hub_path)

    return generated_hubs
