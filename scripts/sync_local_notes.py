#!/usr/bin/env python3
"""Zero-context-overhead multi-session & fork synchronizer for Antigravity (`local-recap` skill).

Thin CLI entrypoint and backwards-compatible public API façade around the `local_recap` package:
  - `local_recap.models`             : Typed `@dataclass` models & formatting helpers
  - `local_recap.git_telemetry`      : Branch tips, recent commits, and live working tree diff state
  - `local_recap.sqlite_metadata`    : Ground-truth SQLite (`conversation_summaries.db`) & protobuf parser
  - `local_recap.transcript_scanner` : Session transcript scanner & Multi-Root Fork/Subagent Forest builder
  - `local_recap.artifact_sync`      : Canonical Markdown/image/HTML/PDF discovery & `.local-notes/` shortcuts
  - `local_recap.hub_renderer`       : Top-of-Hub General Dashboard, 256k/1M context meter, & `PROJECT_HUB.md` writer
  - `local_recap.cli`                : CLI parser, workspace sync runner, and lifecycle hook handler
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from local_recap import *  # noqa: F401, F403, E402
from local_recap import __all__, main  # noqa: F401, E402


if __name__ == "__main__":
    main()
