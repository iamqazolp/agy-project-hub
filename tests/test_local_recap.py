"""Unit and integration test suite for `local_recap` (`agy-project-hub`)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from local_recap import (
    SessionTranscriptCache,
    normalize_workspace_variants,
    parse_parent_reference_blob,
    parse_workspace_uris,
    reconstruct_fork_forest,
    scan_brain_sessions,
)
from sync_local_notes import run_sync


def _encode_varint(val: int) -> bytes:
    out = bytearray()
    while True:
        b = val & 0x7F
        val >>= 7
        if val:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _build_parent_ref_blob(traj_uuid: str, fork_step: int, parent_sid: str) -> bytes:
    t_bytes = traj_uuid.encode("ascii")
    p_bytes = parent_sid.encode("ascii")
    return (
        bytes([0x0A, len(t_bytes)])
        + t_bytes
        + bytes([0x10])
        + _encode_varint(fork_step)
        + bytes([0x32, len(p_bytes)])
        + p_bytes
    )


class TestLocalRecap(unittest.TestCase):
    def test_parse_parent_reference_blob(self) -> None:
        traj_id = "11111111-2222-3333-4444-555555555555"
        parent_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        blob = _build_parent_ref_blob(traj_id, 535, parent_id)
        decoded_parent, decoded_step = parse_parent_reference_blob(blob)
        self.assertEqual(decoded_parent, parent_id)
        self.assertEqual(decoded_step, 535)

    def test_workspace_uri_normalization(self) -> None:
        uris = json.dumps(["file:///Users/dev/My%20Project/"])
        parsed = parse_workspace_uris(uris)
        self.assertIn("/users/dev/my project", parsed)
        self.assertEqual(normalize_workspace_variants("file:///Users/dev/My%20Project"), parsed)

    def test_session_transcript_cache_hit_and_invalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cache_file = tmp_path / ".session_cache.json"
            transcript = tmp_path / "transcript.jsonl"
            transcript.write_text('{"step_index": 0}\n', encoding="utf-8")

            cache = SessionTranscriptCache(cache_file)
            self.assertIsNone(cache.get("sess-1", transcript))

            cache.put("sess-1", transcript, {"first_step": 0, "last_step": 0})
            cache.save()

            cache2 = SessionTranscriptCache(cache_file)
            self.assertEqual(cache2.get("sess-1", transcript), {"first_step": 0, "last_step": 0})

            # Append a new step and verify cache invalidates automatically
            transcript.write_text('{"step_index": 0}\n{"step_index": 1}\n', encoding="utf-8")
            self.assertIsNone(cache2.get("sess-1", transcript))

    def test_reconstruct_fork_forest_and_subagents(self) -> None:
        root_id = "10000000-0000-0000-0000-000000000001"
        fork_id = "20000000-0000-0000-0000-000000000002"
        sub_id = "30000000-0000-0000-0000-000000000003"
        sessions = [
            {
                "id": root_id,
                "first_ts_iso": "2026-10-01T10:00:00Z",
                "last_ts_iso": "2026-10-01T10:30:00Z",
                "first_step": 0,
                "last_step": 50,
                "step_timestamps": {0: "2026-10-01T10:00:00Z", 25: "2026-10-01T10:15:00Z"},
                "step_end_tokens": {25: 80000},
                "first_planner_ctx_tokens": 12000,
                "raw_head_snippet": "",
                "db_ancestry": [],
                "subagent_parent_id": "",
                "nesting_depth": 0,
                "is_subagent": False,
                "parent_id": None,
                "root_id": root_id,
                "fork_depth": 0,
                "fork_step": None,
            },
            {
                "id": fork_id,
                "first_ts_iso": "2026-10-01T10:16:00Z",
                "last_ts_iso": "2026-10-01T10:40:00Z",
                "first_step": 26,
                "last_step": 60,
                "step_timestamps": {26: "2026-10-01T10:16:00Z"},
                "step_end_tokens": {26: 82000},
                "first_planner_ctx_tokens": 80500,
                "raw_head_snippet": "",
                "db_ancestry": [],
                "subagent_parent_id": "",
                "nesting_depth": 0,
                "is_subagent": False,
                "parent_id": None,
                "root_id": fork_id,
                "fork_depth": 0,
                "fork_step": None,
            },
            {
                "id": sub_id,
                "first_ts_iso": "2026-10-01T10:15:30Z",
                "last_ts_iso": "2026-10-01T10:18:00Z",
                "first_step": 0,
                "last_step": 10,
                "step_timestamps": {0: "2026-10-01T10:15:30Z"},
                "step_end_tokens": {0: 15000},
                "first_planner_ctx_tokens": 15000,
                "raw_head_snippet": "",
                "db_ancestry": [],
                "subagent_parent_id": root_id,
                "nesting_depth": 1,
                "is_subagent": True,
                "parent_id": None,
                "root_id": sub_id,
                "fork_depth": 0,
                "fork_step": None,
            },
        ]
        reconstruct_fork_forest(sessions)
        by_id = {s["id"]: s for s in sessions}
        self.assertIsNone(by_id[root_id]["parent_id"])
        self.assertEqual(by_id[fork_id]["parent_id"], root_id)
        self.assertEqual(by_id[fork_id]["fork_step"], 25)
        self.assertEqual(by_id[fork_id]["root_id"], root_id)
        self.assertEqual(by_id[sub_id]["parent_id"], root_id)
        self.assertTrue(by_id[sub_id]["is_subagent"])
        self.assertEqual(by_id[sub_id]["fork_step"], 25)

    def test_end_to_end_sync_and_boundary_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws_a = root / "app"
            ws_b = root / "app-v2"
            ws_a.mkdir()
            ws_b.mkdir()

            brain_dir = root / "brain"
            sid_a = "aaaaaaaa-1111-2222-3333-444444444444"
            sid_b = "bbbbbbbb-1111-2222-3333-444444444444"

            conv_a = brain_dir / sid_a
            (conv_a / ".system_generated" / "logs").mkdir(parents=True)
            (conv_a / ".system_generated" / "logs" / "transcript.jsonl").write_text(
                json.dumps(
                    {
                        "step_index": 0,
                        "type": "USER_INPUT",
                        "created_at": "2026-10-29T10:00:00Z",
                        "content": f"Working in {ws_a}\n<USER_REQUEST>\nWrite architecture guide\n</USER_REQUEST>",
                        "input_tokens": 15000,
                        "cache_read_tokens": 5000,
                        "output_tokens": 1200,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            note_a = conv_a / "architecture_guide.md"
            note_a.write_text("# Architecture Guide\n\n## Core Pipeline\nDetails here.\n", encoding="utf-8")

            conv_b = brain_dir / sid_b
            (conv_b / ".system_generated" / "logs").mkdir(parents=True)
            (conv_b / ".system_generated" / "logs" / "transcript.jsonl").write_text(
                json.dumps(
                    {
                        "step_index": 0,
                        "type": "USER_INPUT",
                        "created_at": "2026-10-29T11:00:00Z",
                        "content": f"Working in {ws_b}\n<USER_REQUEST>\nOther repo prompt\n</USER_REQUEST>",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            cache_file = root / ".cache.json"
            sessions, _, _ = scan_brain_sessions(brain_dir, ws_a, cache_path=cache_file)
            self.assertEqual([s["id"] for s in sessions], [sid_a])

            hubs = run_sync(ws_a, brain_dir, session_id=sid_a, quiet=True, cache_path=cache_file)
            self.assertEqual(len(hubs), 1)
            hub_text = hubs[0].read_text(encoding="utf-8")
            # Session ID is rendered as selectable inline code outside the link
            self.assertIn(f"`{sid_a}` · [↗ Open](conversation://{sid_a})", hub_text)
            # Shortcut is a symlink in .local-notes/
            shortcut = ws_a / ".local-notes" / "architecture_guide.md"
            self.assertTrue(shortcut.is_symlink())
            self.assertEqual(shortcut.resolve(), note_a.resolve())


if __name__ == "__main__":
    unittest.main()
