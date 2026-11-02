"""Unit and integration test suite for the modular `local_recap` (`agy-project-hub`) package."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_local_notes as sln  # noqa: E402
from local_recap import (  # noqa: E402
    SessionInfo,
    collect_git_state,
    file_url,
    format_context_meter,
    format_size,
    format_tokens,
    parse_parent_reference_blob,
    run_sync,
    scan_brain_sessions,
)


class TestModelsAndFormatting(unittest.TestCase):
    def test_token_and_size_formatting(self) -> None:
        self.assertEqual(format_tokens(850), "850")
        self.assertEqual(format_tokens(197_500), "197.5k")
        self.assertEqual(format_tokens(1_350_000), "1.35M")
        self.assertEqual(format_size(512), "512 B")
        self.assertEqual(format_size(96_256), "94 KB")
        self.assertEqual(format_size(12 * 1024 * 1024), "12.0 MB")

    def test_file_url_encodes_spaces(self) -> None:
        url = file_url("/Users/test/QARE_prep/phase1_mcq_prep/Start Simulator.command")
        self.assertEqual(
            url,
            "file:///Users/test/QARE_prep/phase1_mcq_prep/Start%20Simulator.command",
        )

    def test_dual_256k_and_1m_context_meter(self) -> None:
        s_fresh = SessionInfo(
            id="11111111-1111-1111-1111-111111111111",
            title="Fresh",
            path=Path("/tmp"),
            first_ts_iso="",
            last_ts_iso="",
            started_local="",
            last_active="",
            mtime=0.0,
            current_ctx_tokens=51_200,
            peak_ctx_tokens=51_200,
            compaction_count=0,
        )
        m_fresh = format_context_meter(s_fresh)
        self.assertIn("🟢", m_fresh)
        self.assertIn("`20%` of `256k` compact", m_fresh)
        self.assertIn("`5%` of `1M` max", m_fresh)

        s_near_256k = SessionInfo(
            id="22222222-2222-2222-2222-222222222222",
            title="Near 256k",
            path=Path("/tmp"),
            first_ts_iso="",
            last_ts_iso="",
            started_local="",
            last_active="",
            mtime=0.0,
            current_ctx_tokens=197_500,
            peak_ctx_tokens=255_100,
            compaction_count=5,
        )
        m_near = format_context_meter(s_near_256k)
        self.assertIn("🟠", m_near)
        self.assertIn("`77%` of `256k` compact", m_near)
        self.assertIn("`20%` of `1M` max", m_near)
        self.assertIn("`5x compacted`", m_near)
        self.assertIn("only `20%` used if on a 1M model", m_near)

        s_1m_tier = SessionInfo(
            id="33333333-3333-3333-3333-333333333333",
            title="1M Model",
            path=Path("/tmp"),
            first_ts_iso="",
            last_ts_iso="",
            started_local="",
            last_active="",
            mtime=0.0,
            current_ctx_tokens=450_000,
            peak_ctx_tokens=600_000,
            compaction_count=1,
        )
        m_1m = format_context_meter(s_1m_tier)
        self.assertIn("`45%` of `1M` window", m_1m)
        self.assertIn("1M context window active", m_1m)
        self.assertEqual(s_1m_tier["current_ctx_tokens"], 450_000)


class TestProtobufAndScanner(unittest.TestCase):
    def test_parse_parent_reference_blob(self) -> None:
        traj_uuid = b"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        parent_uuid = b"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        # Field 1 (0x0a, len 36) + Field 2 (0x10, varint 42) + Field 6 (0x32, len 36)
        blob = b"\x0a\x24" + traj_uuid + b"\x10\x2a" + b"\x32\x24" + parent_uuid
        psid, fstep = parse_parent_reference_blob(blob)
        self.assertEqual(psid, "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        self.assertEqual(fstep, 42)

    def test_end_to_end_sync_and_hub_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_path = Path(tmp)
            workspace = root_path / "demo_project"
            workspace.mkdir(parents=True)
            (workspace / "app.py").write_text("print('hello')\n", encoding="utf-8")
            (workspace / "dashboard.html").write_text("<html></html>\n", encoding="utf-8")

            subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, check=True)
            subprocess.run(["git", "add", "app.py", "dashboard.html"], cwd=workspace, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=workspace, check=True, capture_output=True)

            # Modify app.py so working tree is dirty
            (workspace / "app.py").write_text("print('hello')\nprint('world')\n", encoding="utf-8")

            brain_dir = root_path / "brain"
            root_sid = "11111111-2222-3333-4444-555555555555"
            fork_sid = "66666666-7777-8888-9999-aaaaaaaaaaaa"

            for sid in (root_sid, fork_sid):
                (brain_dir / sid / ".system_generated" / "logs").mkdir(parents=True)

            # Write a markdown guide in root session
            guide_path = brain_dir / root_sid / "architecture_guide.md"
            guide_path.write_text(
                "# System Architecture\n\nDetailed overview of the demo project.\n\n## Core Pipeline\n\n```mermaid\nflowchart LR\n  A --> B\n```\n",
                encoding="utf-8",
            )

            ws_str = str(workspace.resolve())
            root_steps = [
                {
                    "step_index": 0,
                    "type": "USER_INPUT",
                    "created_at": "2026-11-01T10:00:00Z",
                    "content": f"<USER_REQUEST>Build {ws_str}</USER_REQUEST>",
                },
                {
                    "step_index": 1,
                    "type": "PLANNER_RESPONSE",
                    "created_at": "2026-11-01T10:01:00Z",
                    "input_tokens": 20000,
                    "cache_read_tokens": 5000,
                    "output_tokens": 1200,
                    "tool_calls": [
                        {"name": "write_file", "args": {"Path": str(workspace.resolve() / "app.py")}},
                        {"name": "write_file", "args": {"Path": str(guide_path)}},
                    ],
                },
            ]
            (brain_dir / root_sid / ".system_generated" / "logs" / "transcript.jsonl").write_text(
                "\n".join(json.dumps(x) for x in root_steps) + "\n",
                encoding="utf-8",
            )

            fork_steps = [
                {
                    "step_index": 2,
                    "type": "USER_INPUT",
                    "created_at": "2026-11-01T10:05:00Z",
                    "content": f"<USER_REQUEST>Forked session in {ws_str} from {root_sid}</USER_REQUEST>",
                },
                {
                    "step_index": 3,
                    "type": "PLANNER_RESPONSE",
                    "created_at": "2026-11-01T10:06:00Z",
                    "input_tokens": 21200,
                    "cache_read_tokens": 5000,
                    "output_tokens": 800,
                },
            ]
            (brain_dir / fork_sid / ".system_generated" / "logs" / "transcript.jsonl").write_text(
                "\n".join(json.dumps(x) for x in fork_steps) + "\n",
                encoding="utf-8",
            )

            sessions, _, _ = scan_brain_sessions(brain_dir, workspace)
            self.assertEqual(len(sessions), 2)
            by_id = {s.id: s for s in sessions}
            self.assertIsNone(by_id[root_sid].parent_id)
            self.assertEqual(by_id[fork_sid].parent_id, root_sid)
            self.assertEqual(by_id[fork_sid].fork_step, 1)

            git_state = collect_git_state(workspace)
            self.assertEqual(git_state.current_branch, "main")
            self.assertFalse(git_state.working_tree.clean)
            self.assertEqual(git_state.working_tree.modified, 1)

            hubs = run_sync(workspace, brain_dir, session_id=root_sid, quiet=True)
            self.assertEqual(len(hubs), 2)
            hub_text = (brain_dir / root_sid / "PROJECT_HUB.md").read_text(encoding="utf-8")

            # Verify Top-of-Hub General Dashboard & 5 features
            self.assertIn("| 📚 Knowledge Base | 🌱 Primary Sessions |", hub_text)
            self.assertIn("Context Meter (`256k` / `1M`):", hub_text)
            self.assertIn("🟡 **Dirty (`1 modified`", hub_text)
            self.assertIn("[`app.py`](file:///", hub_text)
            self.assertIn("Interactive HTML Apps & PDF Exports", hub_text)
            self.assertIn("Recent Commits on `main`", hub_text)
            self.assertIn(f"| `{root_sid}` |", hub_text)
            self.assertNotIn("[↗ Open]", hub_text)
            self.assertTrue((workspace / ".local-notes" / "PROJECT_HUB.md").exists())


if __name__ == "__main__":
    unittest.main()
