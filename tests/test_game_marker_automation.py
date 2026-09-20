from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from server import game_marker_automation as gma
from server.game_marker_automation import (
    GameMarkerController,
    invalidate_calibration_cache,
    load_calibration_cache,
    save_calibration_cache,
    solve_mouse_delta,
)


class FakeGameInput:
    def __init__(self, focus: bool = True, escape: bool = False) -> None:
        self.focus = focus
        self.escape = escape
        self.position = [500, 500]
        self.coordinate = [0.0, 0.0]
        self.clicks = 0
        self.enters = 0
        self.released = False
        self.key_taps: list[str] = []

    def focus_game(self) -> bool:
        return self.focus

    def game_is_foreground(self) -> bool:
        return self.focus

    def cursor(self):
        return tuple(self.position)

    def move_cursor(self, x: int, y: int) -> None:
        dx = x - self.position[0]
        dy = y - self.position[1]
        self.position[:] = [x, y]
        self.coordinate[0] += dx
        self.coordinate[1] += dy

    def tap_key(self, key: str, duration: float) -> None:
        self.tap_keys([key], duration)

    def tap_keys(self, keys: list[str], duration: float) -> None:
        scale = duration / 0.08
        vectors = {"W": (0, -8), "S": (0, 8), "D": (8, 0), "A": (-8, 0)}
        for key in keys:
            self.key_taps.append(key)
            if key in vectors:
                self.coordinate[0] += vectors[key][0] * scale
                self.coordinate[1] += vectors[key][1] * scale

    def left_click(self) -> None:
        self.clicks += 1

    def press_enter(self) -> None:
        self.enters += 1

    def escape_pressed(self) -> bool:
        return self.escape

    def release_movement_keys(self) -> None:
        self.released = True


class GameMarkerAutomationTest(unittest.TestCase):
    def run_controller(
        self,
        game_input,
        reader,
        target=(40, -30),
        confirm=True,
        calibration_only=False,
        cache_key: str = "test-monitor",
    ):
        state = {}

        def update(**changes):
            state.update(changes)

        controller = GameMarkerController(
            reader,
            update,
            game_input=game_input,
            timeout_seconds=2,
            sleep=lambda _seconds: None,
            cache_key=cache_key,
        )
        self.assertTrue(
            controller.start(
                target,
                (450, 475, 550, 525),
                (500, 500),
                confirm,
                calibration_only,
                (500, 700),
            )
        )
        controller._thread.join(2)
        self.assertFalse(controller.active)
        state["_timing"] = controller.timing
        state["_controller"] = controller
        return state

    def test_converges_and_confirms_only_on_exact_target(self):
        game_input = FakeGameInput()
        state = self.run_controller(
            game_input,
            lambda _box: (round(game_input.coordinate[0]), round(game_input.coordinate[1])),
        )
        self.assertEqual("completed", state["status"])
        self.assertEqual([40, -30], state["current"])
        self.assertEqual(1, game_input.clicks)
        self.assertEqual(0, game_input.enters)
        self.assertTrue(game_input.released)

    def test_dry_run_reaches_target_without_clicking(self):
        game_input = FakeGameInput()
        state = self.run_controller(
            game_input,
            lambda _box: (round(game_input.coordinate[0]), round(game_input.coordinate[1])),
            confirm=False,
        )
        self.assertEqual("completed", state["status"])
        self.assertIn("calibration", state)
        self.assertEqual(0, game_input.clicks)
        self.assertEqual(0, game_input.enters)

    def test_calibration_only_does_not_move_to_target(self):
        game_input = FakeGameInput()
        state = self.run_controller(
            game_input,
            lambda _box: (round(game_input.coordinate[0]), round(game_input.coordinate[1])),
            confirm=False,
            calibration_only=True,
        )
        self.assertEqual("completed", state["status"])
        self.assertNotEqual([40, -30], state["current"])
        self.assertEqual(0, game_input.clicks)
        self.assertEqual(["W", "D"], game_input.key_taps)

    def test_stops_when_palworld_does_not_have_focus(self):
        game_input = FakeGameInput(focus=False)
        state = self.run_controller(game_input, lambda _box: (0, 0))
        self.assertEqual("error", state["status"])
        self.assertIn("focus", state["error"].lower())
        self.assertEqual(0, game_input.clicks)

    def test_stops_immediately_when_palworld_loses_focus(self):
        game_input = FakeGameInput()

        def read(_box):
            game_input.focus = False
            return 0, 0

        state = self.run_controller(game_input, read)
        self.assertEqual("error", state["status"])
        self.assertIn("lost focus", state["error"].lower())
        self.assertEqual(0, game_input.clicks)

    def test_stops_after_ocr_failure_without_clicking(self):
        game_input = FakeGameInput()
        state = self.run_controller(game_input, lambda _box: None)
        self.assertEqual("error", state["status"])
        self.assertIn("ocr", state["error"].lower())
        self.assertEqual(0, game_input.clicks)

    def test_escape_cancels_and_releases_keys(self):
        game_input = FakeGameInput(escape=True)
        state = self.run_controller(game_input, lambda _box: (0, 0))
        self.assertEqual("cancelled", state["status"])
        self.assertEqual(0, game_input.clicks)
        self.assertTrue(game_input.released)

    def test_rejects_singular_mouse_calibration(self):
        self.assertIsNone(solve_mouse_delta((10, 10), (1, 1), (2, 2)))

    def test_accelerates_only_when_far_from_the_target(self):
        controller = GameMarkerController(lambda _box: (0, 0), lambda **_changes: None)
        vectors = {"W": (0, -8), "S": (0, 8), "D": (8, 0), "A": (-8, 0)}

        _near_key, near_duration = controller._best_key((80, 0), vectors)
        _far_key, far_duration = controller._best_key((200, 0), vectors)

        self.assertLessEqual(near_duration, 0.16)
        self.assertGreater(far_duration, 0.16)
        self.assertLessEqual(far_duration, 0.32)

    def test_reuses_calibration_only_after_a_successful_run(self):
        game_input = FakeGameInput()
        reads = 0

        def read_coordinate(_box):
            nonlocal reads
            reads += 1
            return round(game_input.coordinate[0]), round(game_input.coordinate[1])

        controller = GameMarkerController(
            read_coordinate,
            lambda **_changes: None,
            game_input=game_input,
            timeout_seconds=2,
            sleep=lambda _seconds: None,
            cache_key="mem-reuse",
        )
        arguments = ((40, -30), (450, 475, 550, 525), (500, 500), False, False, None)

        self.assertTrue(controller.start(*arguments))
        controller._thread.join(2)
        first_run_taps = len(game_input.key_taps)
        first_run_reads = reads
        game_input.key_taps.clear()

        self.assertTrue(controller.start(*arguments))
        controller._thread.join(2)
        second_run_reads = reads - first_run_reads

        self.assertGreaterEqual(first_run_taps, 2)
        self.assertEqual([], game_input.key_taps)
        self.assertLess(second_run_reads, first_run_reads)

    def test_exact_target_required_before_confirm_click(self):
        game_input = FakeGameInput()
        # Reader always returns near but never exact target after movement starts.
        calls = {"n": 0}

        def read(_box):
            calls["n"] += 1
            x = round(game_input.coordinate[0])
            y = round(game_input.coordinate[1])
            if (x, y) == (40, -30):
                return 39, -30
            return x, y

        state = self.run_controller(game_input, read, target=(40, -30))
        self.assertNotEqual("completed", state["status"])
        self.assertEqual(0, game_input.clicks)

    def test_alternating_ocr_fails_cleanly_without_click(self):
        game_input = FakeGameInput()
        flip = {"n": 0}

        def read(_box):
            flip["n"] += 1
            base = (round(game_input.coordinate[0]), round(game_input.coordinate[1]))
            if flip["n"] % 2 == 0:
                return base[0] + 1, base[1]
            return base

        state = self.run_controller(game_input, read, confirm=True)
        self.assertEqual("error", state["status"])
        self.assertIn("ocr", state["error"].lower())
        self.assertEqual(0, game_input.clicks)

    def test_stable_ocr_still_converges_after_two_equal_reads(self):
        game_input = FakeGameInput()
        state = self.run_controller(
            game_input,
            lambda _box: (round(game_input.coordinate[0]), round(game_input.coordinate[1])),
            confirm=False,
        )
        self.assertEqual("completed", state["status"])
        self.assertEqual([40, -30], state["current"])
        self.assertEqual(0, game_input.clicks)

    def test_mouse_cache_valid_hit_skips_recalibration(self):
        game_input = FakeGameInput()
        calibrate_calls = {"n": 0}
        controller = GameMarkerController(
            lambda _box: (round(game_input.coordinate[0]), round(game_input.coordinate[1])),
            lambda **_changes: None,
            game_input=game_input,
            timeout_seconds=2,
            sleep=lambda _seconds: None,
            cache_key="mouse-valid",
        )
        controller._cached_key_vectors = {
            "W": (0.0, -8.0),
            "S": (0.0, 8.0),
            "D": (8.0, 0.0),
            "A": (-8.0, 0.0),
        }
        controller._cached_mouse_vectors = ((1.0, 0.0), (0.0, 1.0))
        original = controller._calibrate_mouse

        def wrapped(*args, **kwargs):
            calibrate_calls["n"] += 1
            return original(*args, **kwargs)

        controller._calibrate_mouse = wrapped  # type: ignore[method-assign]
        with mock.patch.object(gma, "OPT_MOUSE_CACHE", True):
            with mock.patch.object(gma, "OPT_DISK_CALIBRATION", False):
                self.assertTrue(
                    controller.start(
                        (5, 0),
                        (450, 475, 550, 525),
                        (500, 500),
                        False,
                        False,
                        None,
                    )
                )
                controller._thread.join(2)
        self.assertEqual(0, calibrate_calls["n"])
        self.assertIsNotNone(controller._cached_mouse_vectors)

    def test_mouse_cache_invalid_hit_recalibrates_and_discards(self):
        game_input = FakeGameInput()
        calibrate_calls = {"n": 0}
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cal.json"
            with mock.patch.object(gma, "CALIBRATION_CACHE_PATH", cache_path):
                with mock.patch.object(gma, "OPT_DISK_CALIBRATION", True):
                    with mock.patch.object(gma, "OPT_MOUSE_CACHE", True):
                        save_calibration_cache(
                            {
                                "version": gma.CALIBRATION_CACHE_VERSION,
                                "monitors": {
                                    "mouse-bad": {
                                        "keys": {
                                            "W": [0, -8],
                                            "S": [0, 8],
                                            "D": [8, 0],
                                            "A": [-8, 0],
                                        },
                                        "mouseX": [0.0, 1.0],
                                        "mouseY": [1.0, 0.0],
                                    }
                                },
                            }
                        )
                        controller = GameMarkerController(
                            lambda _box: (
                                round(game_input.coordinate[0]),
                                round(game_input.coordinate[1]),
                            ),
                            lambda **_changes: None,
                            game_input=game_input,
                            timeout_seconds=2,
                            sleep=lambda _seconds: None,
                            cache_key="mouse-bad",
                        )
                        original = controller._calibrate_mouse

                        def wrapped(*args, **kwargs):
                            calibrate_calls["n"] += 1
                            return original(*args, **kwargs)

                        controller._calibrate_mouse = wrapped  # type: ignore[method-assign]
                        self.assertTrue(
                            controller.start(
                                (5, 0),
                                (450, 475, 550, 525),
                                (500, 500),
                                False,
                                False,
                                None,
                            )
                        )
                        controller._thread.join(2)
                        self.assertGreaterEqual(calibrate_calls["n"], 1)
                        entry = load_calibration_cache()["monitors"].get("mouse-bad", {})
                        # Bad orientation must not remain; recalibrated mouse is 1:1 with FakeGameInput.
                        self.assertNotEqual([0.0, 1.0], entry.get("mouseX"))
                        self.assertEqual([1.0, 0.0], entry.get("mouseX"))

    def test_divergence_invalidates_memory_and_disk_cache(self):
        game_input = FakeGameInput()
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cal.json"
            with mock.patch.object(gma, "CALIBRATION_CACHE_PATH", cache_path):
                with mock.patch.object(gma, "OPT_DISK_CALIBRATION", True):
                    save_calibration_cache(
                        {
                            "version": gma.CALIBRATION_CACHE_VERSION,
                            "monitors": {
                                "div-key": {
                                    "keys": {
                                        "W": [0, -8],
                                        "S": [0, 8],
                                        "D": [8, 0],
                                        "A": [-8, 0],
                                    }
                                }
                            },
                        }
                    )
                    controller = GameMarkerController(
                        lambda _box: (
                            round(game_input.coordinate[0]),
                            round(game_input.coordinate[1]),
                        ),
                        lambda **_changes: None,
                        game_input=game_input,
                        timeout_seconds=2,
                        sleep=lambda _seconds: None,
                        cache_key="div-key",
                    )
                    controller._cached_key_vectors = {
                        "W": (0.0, -8.0),
                        "S": (0.0, 8.0),
                        "D": (8.0, 0.0),
                        "A": (-8.0, 0.0),
                    }
                    # Invert movement so each step increases error → 3 regressions.
                    def bad_tap(keys, duration):
                        scale = duration / 0.08
                        vectors = {"W": (0, 8), "S": (0, -8), "D": (-8, 0), "A": (8, 0)}
                        for key in keys:
                            game_input.key_taps.append(key)
                            if key in vectors:
                                game_input.coordinate[0] += vectors[key][0] * scale
                                game_input.coordinate[1] += vectors[key][1] * scale

                    game_input.tap_keys = bad_tap  # type: ignore[method-assign]
                    game_input.coordinate[:] = [40.0, -30.0]
                    self.assertTrue(
                        controller.start(
                            (0, 0),
                            (450, 475, 550, 525),
                            (500, 500),
                            False,
                            False,
                            None,
                        )
                    )
                    controller._thread.join(2)
                    self.assertIsNone(controller._cached_key_vectors)
                    self.assertNotIn("div-key", load_calibration_cache()["monitors"])

    def test_cancel_and_focus_lost_do_not_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cal.json"
            with mock.patch.object(gma, "CALIBRATION_CACHE_PATH", cache_path):
                with mock.patch.object(gma, "OPT_DISK_CALIBRATION", True):
                    save_calibration_cache(
                        {
                            "version": gma.CALIBRATION_CACHE_VERSION,
                            "monitors": {
                                "keep-key": {
                                    "keys": {
                                        "W": [0, -8],
                                        "S": [0, 8],
                                        "D": [8, 0],
                                        "A": [-8, 0],
                                    }
                                }
                            },
                        }
                    )
                    esc_input = FakeGameInput(escape=True)
                    esc_controller = GameMarkerController(
                        lambda _box: (0, 0),
                        lambda **_changes: None,
                        game_input=esc_input,
                        timeout_seconds=2,
                        sleep=lambda _seconds: None,
                        cache_key="keep-key",
                    )
                    esc_controller._cached_key_vectors = {
                        "W": (0.0, -8.0),
                        "S": (0.0, 8.0),
                        "D": (8.0, 0.0),
                        "A": (-8.0, 0.0),
                    }
                    esc_controller.start(
                        (40, -30), (0, 0, 1, 1), (500, 500), False, False, None
                    )
                    esc_controller._thread.join(2)
                    self.assertIsNotNone(esc_controller._cached_key_vectors)
                    self.assertIn("keep-key", load_calibration_cache()["monitors"])

                    focus_input = FakeGameInput(focus=False)
                    focus_controller = GameMarkerController(
                        lambda _box: (0, 0),
                        lambda **_changes: None,
                        game_input=focus_input,
                        timeout_seconds=2,
                        sleep=lambda _seconds: None,
                        cache_key="keep-key",
                    )
                    focus_controller._cached_key_vectors = {
                        "W": (0.0, -8.0),
                        "S": (0.0, 8.0),
                        "D": (8.0, 0.0),
                        "A": (-8.0, 0.0),
                    }
                    focus_controller.start(
                        (40, -30), (0, 0, 1, 1), (500, 500), False, False, None
                    )
                    focus_controller._thread.join(2)
                    self.assertIsNotNone(focus_controller._cached_key_vectors)
                    self.assertIn("keep-key", load_calibration_cache()["monitors"])

    def test_adaptive_settle_returns_early_on_stable_ocr(self):
        game_input = FakeGameInput()
        values = [(1, 1), (1, 1)]
        idx = {"i": 0}

        def read(_box):
            i = min(idx["i"], len(values) - 1)
            idx["i"] += 1
            return values[i]

        sleeps: list[float] = []
        controller = GameMarkerController(
            read,
            lambda **_changes: None,
            game_input=game_input,
            sleep=lambda seconds: sleeps.append(seconds),
            cache_key="settle",
        )
        with mock.patch.object(gma, "OPT_ADAPTIVE_SLEEP", True):
            result = controller._wait_settle(
                (0, 0, 1, 1), (0, 0), time_started := __import__("time").monotonic(), (0, 0), 0.24
            )
        self.assertEqual((1, 1), result)
        self.assertLess(sum(sleeps), 0.24)

    def test_disk_calibration_hit_miss_and_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cal.json"
            with mock.patch.object(gma, "CALIBRATION_CACHE_PATH", cache_path):
                with mock.patch.object(gma, "OPT_DISK_CALIBRATION", True):
                    invalidate_calibration_cache()
                    empty = load_calibration_cache()
                    self.assertEqual({}, empty["monitors"])

                    save_calibration_cache(
                        {
                            "version": gma.CALIBRATION_CACHE_VERSION,
                            "monitors": {
                                "disk-hit": {
                                    "keys": {
                                        "W": [0, -8],
                                        "S": [0, 8],
                                        "D": [8, 0],
                                        "A": [-8, 0],
                                    }
                                }
                            },
                        }
                    )
                    loaded = load_calibration_cache()
                    self.assertIn("disk-hit", loaded["monitors"])

                    game_input = FakeGameInput()
                    state = self.run_controller(
                        game_input,
                        lambda _box: (
                            round(game_input.coordinate[0]),
                            round(game_input.coordinate[1]),
                        ),
                        confirm=False,
                        cache_key="disk-hit",
                    )
                    self.assertEqual("completed", state["status"])
                    # Validation tap W then movement; should not run full W+D calibrate pair first.
                    self.assertNotEqual(["W", "D"], game_input.key_taps[:2])

                    invalidate_calibration_cache("disk-hit")
                    self.assertNotIn("disk-hit", load_calibration_cache()["monitors"])

    def test_dual_axis_plans_two_keys_when_diagonal(self):
        controller = GameMarkerController(lambda _box: (0, 0), lambda **_changes: None)
        vectors = {"W": (0, -8), "S": (0, 8), "D": (8, 0), "A": (-8, 0)}
        with mock.patch.object(gma, "OPT_DUAL_AXIS", True):
            keys, _duration = controller._plan_key_move((40, -30), vectors)
        self.assertEqual(2, len(keys))
        self.assertIn("D", keys)
        self.assertIn("W", keys)

    def test_timing_counts_ocr_and_iterations(self):
        os.environ["PALWORLD_MARKER_TIMING"] = "1"
        try:
            # Re-read flag by constructing timing after patch
            with mock.patch.object(gma, "MARKER_TIMING", True):
                game_input = FakeGameInput()
                state = self.run_controller(
                    game_input,
                    lambda _box: (
                        round(game_input.coordinate[0]),
                        round(game_input.coordinate[1]),
                    ),
                    confirm=False,
                )
                timing = state["_timing"]
                self.assertGreater(timing.ocr_reads, 0)
                self.assertGreater(timing.loop_iterations, 0)
        finally:
            os.environ.pop("PALWORLD_MARKER_TIMING", None)


if __name__ == "__main__":
    unittest.main()
