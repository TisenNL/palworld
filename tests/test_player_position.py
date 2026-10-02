from __future__ import annotations

import io
import struct
import unittest

from server.player_position import (
    ACTOR_POINTER_OFFSET,
    FIRST_OBJECT_POINTER_OFFSET,
    GAME_INSTANCE_LOCAL_PLAYERS_OFFSET,
    LOCAL_PLAYER_CONTROLLER_OFFSET,
    LOCATION_VECTOR_OFFSET,
    PLAYER_CONTROLLER_PAWN_OFFSET,
    WORLD_GAME_INSTANCE_OFFSET,
    _gworld_signature_offsets,
    _position_zone,
    _read_local_player_actor_address,
    _read_player_position_from_memory,
    _scan_gworld_signature,
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
    def test_finds_only_the_validated_unreal_world_signature(self):
        signature = b"\x48\x8b\x05" + b"\x01\x02\x03\x04" + b"\xeb\x05"

        self.assertEqual([3], _gworld_signature_offsets(b"abc" + signature + b"xyz"))
        self.assertEqual([], _gworld_signature_offsets(b"no signature"))
        self.assertEqual(
            [0, 12],
            _gworld_signature_offsets(signature + b"---" + signature),
        )

    def test_finds_signature_split_across_file_read_chunks(self):
        signature = b"\x48\x8b\x05" + b"\x01\x02\x03\x04" + b"\xeb\x05"
        prefix = b"x" * (1024 * 1024 - 4)
        executable = io.BytesIO(prefix + signature)

        self.assertEqual(
            [0x400000 + len(prefix)],
            _scan_gworld_signature(
                executable,
                0,
                len(prefix) + len(signature),
                0x400000,
            ),
        )

    def test_follows_unreal_local_player_chain_to_the_character(self):
        world = 0x10000
        game_instance = 0x11000
        local_players = 0x12000
        local_player = 0x13000
        player_controller = 0x14000
        player_character = 0x15000
        memory = {
            world + WORLD_GAME_INSTANCE_OFFSET: struct.pack("<Q", game_instance),
            game_instance + GAME_INSTANCE_LOCAL_PLAYERS_OFFSET: struct.pack(
                "<Qii",
                local_players,
                1,
                1,
            ),
            local_players: struct.pack("<Q", local_player),
            local_player + LOCAL_PLAYER_CONTROLLER_OFFSET: struct.pack(
                "<Q",
                player_controller,
            ),
            player_controller + PLAYER_CONTROLLER_PAWN_OFFSET: struct.pack(
                "<Q",
                player_character,
            ),
        }

        def read_memory(address: int, _size: int) -> bytes | None:
            return memory.get(address)

        self.assertEqual(
            player_character,
            _read_local_player_actor_address(world, read_memory),
        )

    def test_rejects_invalid_local_player_array(self):
        world = 0x10000
        game_instance = 0x11000
        memory = {
            world + WORLD_GAME_INSTANCE_OFFSET: struct.pack("<Q", game_instance),
            game_instance + GAME_INSTANCE_LOCAL_PLAYERS_OFFSET: struct.pack(
                "<Qii",
                0x12000,
                0,
                0,
            ),
        }

        self.assertIsNone(
            _read_local_player_actor_address(
                world,
                lambda address, _size: memory.get(address),
            )
        )

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
