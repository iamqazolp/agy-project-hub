"""Typed data models and formatting helpers for `local-recap` (`agy-project-hub`)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class DictCompatMixin:
    """Provide backwards-compatible dictionary-style access (`obj['key']`, `obj.get('key')`)
    alongside typed attribute access (`obj.key`) for smooth migration and test compatibility.
    """

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)


@dataclass
class AncestryLink(DictCompatMixin):
    idx: int
    parent_id: str
    fork_step: int | None = None


@dataclass
class SqliteSessionMeta(DictCompatMixin):
    matched_workspace: bool = False
    known_other_workspace: bool = False
    title: str = ""
    db_step_count: int = 0
    subagent_parent_id: str = ""
    agent_name: str = ""
    nesting_depth: int = 0
    ancestry: list[AncestryLink] = field(default_factory=list)


@dataclass
class PromptEntry(DictCompatMixin):
    step: int
    timestamp: str
    text: str


@dataclass
class TouchEvent(DictCompatMixin):
    rel: str
    abs: str
    ts_iso: str
    ts_local: str
    session_id: str


@dataclass
class SessionInfo(DictCompatMixin):
    id: str
    title: str
    path: Path
    first_ts_iso: str
    last_ts_iso: str
    started_local: str
    last_active: str
    mtime: float
    first_step: int = 0
    last_step: int = 0
    step_timestamps: dict[int, str] = field(default_factory=dict)
    step_end_tokens: dict[int, int] = field(default_factory=dict)
    step_ctx_tokens: dict[int, int] = field(default_factory=dict)
    chat_steps: list[int] = field(default_factory=list)
    first_planner_ctx_tokens: int = 0
    user_chats: int = 0
    inherited_chats: int = 0
    current_ctx_tokens: int = 0
    peak_ctx_tokens: int = 0
    total_output_tokens: int = 0
    compaction_count: int = 0
    inherited_compactions: int = 0
    prompts: list[PromptEntry] = field(default_factory=list)
    artifacts: list[Path] = field(default_factory=list)
    authored_docs: list[str] = field(default_factory=list)
    touched_files: dict[str, TouchEvent] = field(default_factory=dict)
    raw_head_snippet: str = ""
    db_ancestry: list[AncestryLink] = field(default_factory=list)
    subagent_parent_id: str = ""
    agent_name: str = ""
    nesting_depth: int = 0
    is_subagent: bool = False
    parent_id: str | None = None
    root_id: str = ""
    fork_depth: int = 0
    fork_step: int | None = None
    lineage_source: str = "root"
    tree_num: int = 1


@dataclass
class DocStats(DictCompatMixin):
    line_count: int = 0
    h2s: list[str] = field(default_factory=list)
    total_h2s: int = 0
    visual_count: int = 0


@dataclass
class ArtifactDoc(DictCompatMixin):
    name: str
    path: Path
    brain_path: Path
    from_local_backup: bool
    mtime: float
    updated_str: str
    title: str
    priority: int
    category: str
    purpose: str
    summary: str
    origin_sid: str
    stats: DocStats = field(default_factory=DocStats)


@dataclass
class RichMediaItem(DictCompatMixin):
    name: str
    path: Path
    rel_label: str
    ext: str
    mtime: float
    size_bytes: int
    origin_sid: str = ""


@dataclass
class ChangedFile(DictCompatMixin):
    rel: str
    abs: str
    badge: str

    @property
    def status(self) -> str:
        return self.badge


@dataclass
class WorkingTreeState(DictCompatMixin):
    clean: bool = True
    modified: int = 0
    added: int = 0
    deleted: int = 0
    untracked: int = 0
    insertions: int = 0
    deletions: int = 0
    files: list[ChangedFile] = field(default_factory=list)


@dataclass
class BranchTip(DictCompatMixin):
    name: str
    sha: str
    subject: str


@dataclass
class CommitInfo(DictCompatMixin):
    sha: str
    date: str
    refs: str
    subject: str
    parents: list[str] = field(default_factory=list)
    author: str = ""


@dataclass
class GitState(DictCompatMixin):
    current_branch: str = "detached"
    branches: list[BranchTip] = field(default_factory=list)
    commits: list[CommitInfo] = field(default_factory=list)
    graph_commits: list[CommitInfo] = field(default_factory=list)
    status: str = ""
    working_tree: WorkingTreeState = field(default_factory=WorkingTreeState)


def utc_iso_to_local_str(iso_str: str, include_seconds: bool = False) -> str:
    """Convert an ISO-8601 timestamp (e.g. `2026-10-26T17:48:32Z`) to local wall-clock time."""
    if not iso_str:
        return ""
    try:
        cleaned = iso_str.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(cleaned)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        fmt = "%Y-%m-%d %H:%M:%S" if include_seconds else "%Y-%m-%d %H:%M"
        return parsed.strftime(fmt)
    except Exception:
        return iso_str[:19].replace("T", " ")


def format_tokens(n: int) -> str:
    """Format token counts cleanly (`1.35M`, `197.5k`, `850`)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000.0:.2f}M"
    if n >= 1000:
        return f"{n / 1000.0:.1f}k"
    return str(n)


def format_size(num_bytes: int) -> str:
    """Format byte sizes cleanly (`12.0 MB`, `94 KB`, `512 B`)."""
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024.0 * 1024.0):.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024.0:.0f} KB"
    return f"{num_bytes} B"


def file_url(path_or_str: str | Path) -> str:
    """Convert an absolute filesystem path into a normalized, space-encoded `file:///` URL."""
    norm = str(path_or_str).replace("\\", "/").lstrip("/").replace(" ", "%20")
    return f"file:///{norm}"
