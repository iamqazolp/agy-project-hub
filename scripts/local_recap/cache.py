"""Incremental transcript & session metadata cache keyed by `(session_id, mtime_ns, size)`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CACHE_SCHEMA_VERSION = 1


def default_cache_path() -> Path:
    return Path.home() / ".gemini" / "config" / "skills" / "local-recap" / ".session_cache.json"


class SessionTranscriptCache:
    """Caches parsed `transcript.jsonl` summaries so unchanged historical sessions are not re-parsed
    on every `PostInvocation` hook execution.
    """

    def __init__(self, cache_path: Path | None = None) -> None:
        self.cache_path = cache_path or default_cache_path()
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(raw, dict) and raw.get("version") == CACHE_SCHEMA_VERSION:
                entries = raw.get("entries")
                if isinstance(entries, dict):
                    self._entries = entries
        except Exception:
            self._entries = {}

    def get(self, session_id: str, transcript_path: Path) -> dict[str, Any] | None:
        if not transcript_path.exists():
            return None
        try:
            st = transcript_path.stat()
        except OSError:
            return None
        entry = self._entries.get(session_id)
        if not isinstance(entry, dict):
            return None
        if entry.get("mtime_ns") == st.st_mtime_ns and entry.get("size") == st.st_size:
            data = entry.get("data")
            if isinstance(data, dict):
                return data
        return None

    def put(self, session_id: str, transcript_path: Path, data: dict[str, Any]) -> None:
        if not transcript_path.exists():
            return
        try:
            st = transcript_path.stat()
        except OSError:
            return
        self._entries[session_id] = {
            "mtime_ns": st.st_mtime_ns,
            "size": st.st_size,
            "data": data,
        }
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": CACHE_SCHEMA_VERSION,
                "entries": self._entries,
            }
            self.cache_path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
            self._dirty = False
        except Exception:
            pass
