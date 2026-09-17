from __future__ import annotations

import unittest

from server.game_marker_automation import GameMarkerController, solve_mouse_delta


class FakeGameInput:
    def __init__(self, focus: bool = True, escape: bool = False) -> None:
        self.focus = focus
        self.escape = escape
        self.position = [500, 500]
        self.coordinate = [0.0, 0.0]
        self.clicks = 0
        self.enters = 0
        self.released = False

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
        scale = duration / 0.08
        vectors = {"W": (0, -8), "S": (0, 8), "D": (8, 0), "A": (-8, 0)}
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
        self, game_input, reader, target=(40, -30), confirm=True, calibration_only=False
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


if __name__ == "__main__":
    unittest.main()
