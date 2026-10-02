from __future__ import annotations

import unittest
import struct

from server.player_position import (
    ACTOR_POINTER_OFFSET,
    FIRST_OBJECT_POINTER_OFFSET,
    LOCATION_VECTOR_OFFSET,
    _parse_overwolf_actor_address,
    _position_zone,
    _read_player_position_from_memory,
    probe_palworld_process,
)


class PalworldProcessProbeTest(unittest.TestCase):
    def test_reports_ready_for_exact_shipping_process_with_read_access(self):
        checked: list[int] = []

        def check_access(pid: int) -> tuple[bool, int]:
            checked.append(pid)
            return True, 0

        result = probe_palworld_process(
            process_entries=lambda: [
                (10, "Palworld.exe"),
                (20, "Palworld-Win64-Shipping.exe"),
                (30, "Palworld-WinGDK-Shipping.exe"),
            ],
            read_access=check_access,
        )

        self.assertEqual(
            {
                "ok": True,
                "status": "ready",
                "processFound": True,
                "readAccess": True,
                "pid": 20,
                "error": "",
            },
            result,
        )
        self.assertEqual([20], checked)
        self.assertNotIn("position", result)

    def test_reports_not_running_when_shipping_process_is_absent(self):
        def fail_if_called(_pid: int) -> tuple[bool, int]:
            self.fail("read access should not be checked when the game is absent")

        result = probe_palworld_process(
            process_entries=lambda: [(10, "Palworld.exe")],
            read_access=fail_if_called,
        )

        self.assertEqual("not_running", result["status"])
        self.assertFalse(result["processFound"])
        self.assertFalse(result["readAccess"])
        self.assertIsNone(result["pid"])

    def test_reports_access_denied_without_trying_to_read_memory(self):
        result = probe_palworld_process(
            process_entries=lambda: [(20, "Palworld-Win64-Shipping.exe")],
            read_access=lambda _pid: (False, 5),
        )

        self.assertEqual("access_denied", result["status"])
        self.assertTrue(result["processFound"])
        self.assertFalse(result["readAccess"])
        self.assertEqual(20, result["pid"])
        self.assertEqual("Access denied", result["error"])

    def test_reports_other_open_errors_explicitly(self):
        result = probe_palworld_process(
            process_entries=lambda: [(20, "Palworld-Win64-Shipping.exe")],
            read_access=lambda _pid: (False, 87),
        )

        self.assertEqual("probe_error", result["status"])
        self.assertIn("87", result["error"])


class PalworldPositionReaderTest(unittest.TestCase):
    def test_parses_newest_player_actor_address_without_requiring_coordinates(self):
        first = (
            '2026-10-02 10:00:00,000 (INFO) - Got first player '
            '{"action":"player","payload":{"address":1234,"x":1,"y":2,"z":3}}'
        )
        latest = (
            '2026-10-02 10:01:00,000 (INFO) - Got first player '
            '{"action":"player","payload":{"address":5678}}'
        )

        result = _parse_overwolf_actor_address([first, latest])

        self.assertIsNotNone(result)
        self.assertEqual(5678, result[0])
        self.assertGreater(result[1], 0)

    def test_ignores_malformed_or_invalid_player_messages(self):
        lines = [
            "Got first player not-json",
            '2026-10-02 10:00:00,000 Got first player {"payload":{"address":0}}',
        ]

        self.assertIsNone(_parse_overwolf_actor_address(lines))

    def test_reads_player_position_through_validated_pointer_chain(self):
        actor = 0x1000
        first = 0x2000
        second = 0x3000
        expected = (100.0, 200.0, 300.0)
        memory = {
            actor + ACTOR_POINTER_OFFSET: struct.pack("<Q", first),
            first + FIRST_OBJECT_POINTER_OFFSET: struct.pack("<Q", second),
            second + LOCATION_VECTOR_OFFSET: struct.pack("<ddd", *expected),
        }

        result = _read_player_position_from_memory(actor, memory.get)

        self.assertEqual(expected, result)

    def test_rejects_invalid_or_out_of_map_position(self):
        actor = 0x1000
        first = 0x2000
        second = 0x3000
        memory = {
            actor + ACTOR_POINTER_OFFSET: struct.pack("<Q", first),
            first + FIRST_OBJECT_POINTER_OFFSET: struct.pack("<Q", second),
            second + LOCATION_VECTOR_OFFSET: struct.pack("<ddd", 9_000_000, 0, 0),
        }

        self.assertIsNone(_read_player_position_from_memory(actor, memory.get))
        self.assertEqual("palpagos", _position_zone(0, 0))
        self.assertEqual("world-tree", _position_zone(500_000, -600_000))
        self.assertIsNone(_position_zone(9_000_000, 0))


if __name__ == "__main__":
    unittest.main()
