"""Modular `local-recap` package for multi-session & fork telemetry synchronization."""

from __future__ import annotations

from .cache import SessionTranscriptCache, default_cache_path
from .hub_renderer import (
    rewrite_md_images_for_brain_dir,
    sync_all_targets,
    sync_local_shortcuts,
    write_artifact_metadata,
)
from .lineage import (
    normalize_workspace_variants,
    parse_parent_reference_blob,
    parse_workspace_uris,
    query_antigravity_sqlite_metadata,
    reconstruct_fork_forest,
)
from .scanner import (
    classify_document,
    collect_canonical_artifacts,
    collect_git_state,
    ensure_git_exclude,
    extract_md_sections_and_stats,
    extract_md_title,
    extract_user_request_text,
    format_tokens,
    scan_brain_sessions,
    sort_canonical_docs,
    utc_iso_to_local_str,
)
from .vscode_integration import (
    bridge_ide_and_cli_brain_sessions,
    ensure_vscode_editor_associations,
)

__all__ = [
    "SessionTranscriptCache",
    "default_cache_path",
    "parse_parent_reference_blob",
    "normalize_workspace_variants",
    "parse_workspace_uris",
    "query_antigravity_sqlite_metadata",
    "reconstruct_fork_forest",
    "ensure_git_exclude",
    "collect_git_state",
    "extract_user_request_text",
    "utc_iso_to_local_str",
    "format_tokens",
    "scan_brain_sessions",
    "extract_md_title",
    "classify_document",
    "extract_md_sections_and_stats",
    "collect_canonical_artifacts",
    "sort_canonical_docs",
    "write_artifact_metadata",
    "rewrite_md_images_for_brain_dir",
    "sync_local_shortcuts",
    "sync_all_targets",
    "ensure_vscode_editor_associations",
    "bridge_ide_and_cli_brain_sessions",
]
