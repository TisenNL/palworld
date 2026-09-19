from __future__ import annotations

import ctypes
import math
import os
import threading
import time
from ctypes import wintypes
from typing import Callable, Optional

Coordinate = tuple[int, int]
Box = tuple[int, int, int, int]
StateUpdater = Callable[..., None]
CoordinateReader = Callable[[Box], Optional[Coordinate]]

VK = {
    "A": 0x41,
    "D": 0x44,
    "E": 0x45,
    "S": 0x53,
    "W": 0x57,
    "ENTER": 0x0D,
    "ESCAPE": 0x1B,
}
KEY_UP = 0x0002
LEFT_DOWN = 0x0002
LEFT_UP = 0x0004
RIGHT_DOWN = 0x0008
RIGHT_UP = 0x0010
MIDDLE_DOWN = 0x0020
MIDDLE_UP = 0x0040
METERS_PER_MAP_COORDINATE = 4.59


def distance_meters(first: Coordinate, second: Coordinate) -> int:
    return round(math.hypot(second[0] - first[0], second[1] - first[1]) * METERS_PER_MAP_COORDINATE)


def solve_mouse_delta(
    error: tuple[float, float],
    mouse_x: tuple[float, float],
    mouse_y: tuple[float, float],
) -> Optional[tuple[float, float]]:
    determinant = mouse_x[0] * mouse_y[1] - mouse_y[0] * mouse_x[1]
    if abs(determinant) < 0.0001:
        return None
    return (
        (error[0] * mouse_y[1] - mouse_y[0] * error[1]) / determinant,
        (mouse_x[0] * error[1] - error[0] * mouse_x[1]) / determinant,
    )


class WindowsGameInput:
    def __init__(self, window_name: str = "Palworld") -> None:
        self.window_name = window_name.casefold()
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    def _window_title(self, hwnd: int) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def _is_game_window(self, hwnd: int, title: str) -> bool:
        process_id = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        process = self.kernel32.OpenProcess(0x1000, False, process_id.value)
        executable = ""
        if process:
            try:
                size = wintypes.DWORD(32768)
                buffer = ctypes.create_unicode_buffer(size.value)
                if self.kernel32.QueryFullProcessImageNameW(
                    process, 0, buffer, ctypes.byref(size)
                ):
                    executable = os.path.basename(buffer.value).casefold()
            finally:
                self.kernel32.CloseHandle(process)
        return executable.startswith("palworld") or title.casefold().strip() == self.window_name

    def find_window(self) -> int:
        handles: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def collect(hwnd: int, _lparam: int) -> bool:
            if not self.user32.IsWindowVisible(hwnd):
                return True
            title = self._window_title(hwnd)
            if self._is_game_window(hwnd, title):
                handles.append(hwnd)
            return True

        self.user32.EnumWindows(callback_type(collect), 0)
        return handles[0] if handles else 0

    def focus_game(self) -> bool:
        hwnd = self.find_window()
        if not hwnd:
            return False
        foreground = self.user32.GetForegroundWindow()
        current_thread = self.kernel32.GetCurrentThreadId()
        target_thread = self.user32.GetWindowThreadProcessId(hwnd, None)
        foreground_thread = (
            self.user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        )
        attached: list[int] = []
        for thread_id in (foreground_thread, target_thread):
            if thread_id and thread_id != current_thread:
                if self.user32.AttachThreadInput(current_thread, thread_id, True):
                    attached.append(thread_id)
        try:
            self.user32.ShowWindowAsync(hwnd, 9)
            self.user32.BringWindowToTop(hwnd)
            self.user32.SetForegroundWindow(hwnd)
            self.user32.SetFocus(hwnd)
        finally:
            for thread_id in reversed(attached):
                self.user32.AttachThreadInput(current_thread, thread_id, False)
        if not self.game_is_foreground():
            self.user32.keybd_event(0x12, 0, 0, 0)
            self.user32.SetForegroundWindow(hwnd)
            self.user32.keybd_event(0x12, 0, KEY_UP, 0)
        time.sleep(0.25)
        return self.game_is_foreground()

    def game_is_foreground(self) -> bool:
        hwnd = self.user32.GetForegroundWindow()
        return bool(hwnd and self._is_game_window(hwnd, self._window_title(hwnd)))

    def cursor(self) -> Coordinate:
        point = wintypes.POINT()
        self.user32.GetCursorPos(ctypes.byref(point))
        return int(point.x), int(point.y)

    def move_cursor(self, x: int, y: int) -> None:
        self.user32.SetCursorPos(int(x), int(y))

    def tap_key(self, key: str, duration: float) -> None:
        code = VK[key]
        self.user32.keybd_event(code, 0, 0, 0)
        try:
            time.sleep(duration)
        finally:
            self.user32.keybd_event(code, 0, KEY_UP, 0)

    def left_click(self) -> None:
        self.user32.mouse_event(LEFT_DOWN, 0, 0, 0, 0)
        self.user32.mouse_event(LEFT_UP, 0, 0, 0, 0)

    def right_button_down(self) -> None:
        self.user32.mouse_event(RIGHT_DOWN, 0, 0, 0, 0)

    def right_button_up(self) -> None:
        self.user32.mouse_event(RIGHT_UP, 0, 0, 0, 0)

    def middle_click(self) -> None:
        self.user32.mouse_event(MIDDLE_DOWN, 0, 0, 0, 0)
        self.user32.mouse_event(MIDDLE_UP, 0, 0, 0, 0)

    def press_enter(self) -> None:
        self.tap_key("ENTER", 0.04)

    def escape_pressed(self) -> bool:
        return bool(self.user32.GetAsyncKeyState(0x1B) & 0x8000)

    def release_movement_keys(self) -> None:
        for key in ("W", "A", "S", "D"):
            self.user32.keybd_event(VK[key], 0, KEY_UP, 0)


class GameMarkerController:
    def __init__(
        self,
        read_coordinate: CoordinateReader,
        update_state: StateUpdater,
        game_input: Optional[WindowsGameInput] = None,
        timeout_seconds: float = 90.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.read_coordinate = read_coordinate
        self.update_state = update_state
        self.game_input = game_input or WindowsGameInput()
        self.timeout_seconds = timeout_seconds
        self.sleep = sleep
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cached_key_vectors: Optional[dict[str, tuple[float, float]]] = None

    @property
    def active(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(
        self,
        target: Coordinate,
        selection_box: Box,
        selection_point: Coordinate,
        confirm: bool = True,
        calibration_only: bool = False,
        add_button: Optional[Coordinate] = None,
    ) -> bool:
        if self.active:
            return False
        self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(
                target,
                selection_box,
                selection_point,
                confirm,
                calibration_only,
                add_button,
            ),
            daemon=True,
        )
        self._thread.start()
        return True

    def cancel(self) -> None:
        self._cancel.set()

    def _check_safety(self, started: float) -> None:
        if self._cancel.is_set() or self.game_input.escape_pressed():
            raise RuntimeError("Automation cancelled")
        if time.monotonic() - started > self.timeout_seconds:
            raise TimeoutError("Automation timed out before reaching the target")
        if not self.game_input.game_is_foreground():
            raise RuntimeError("Palworld lost focus; automation stopped")

    def _translated_box(self, box: Box, origin: Coordinate) -> Box:
        return box

    def _read(self, box: Box, origin: Coordinate, started: float) -> Coordinate:
        previous: Optional[Coordinate] = None
        consecutive = 0
        for _attempt in range(6):
            self._check_safety(started)
            value = self.read_coordinate(self._translated_box(box, origin))
            if value is not None:
                consecutive = consecutive + 1 if value == previous else 1
                previous = value
                if consecutive >= 2:
                    return value
            self.sleep(0.08)
        raise RuntimeError("OCR coordinates are missing or unstable")

    def _read_near(
        self,
        box: Box,
        origin: Coordinate,
        started: float,
        previous: Coordinate,
        maximum_delta: float = 200.0,
    ) -> Coordinate:
        for _attempt in range(3):
            value = self._read(box, origin, started)
            if math.hypot(value[0] - previous[0], value[1] - previous[1]) <= maximum_delta:
                return value
        raise RuntimeError("OCR reported an implausible coordinate jump")

    def _calibrate_mouse(
        self,
        current: Coordinate,
        box: Box,
        origin: Coordinate,
        started: float,
    ) -> tuple[tuple[float, float], tuple[float, float], Coordinate]:
        anchor = self.game_input.cursor()
        vectors: list[tuple[float, float]] = []
        latest = current
        for dx, dy in ((24, 0), (0, 24)):
            self.game_input.move_cursor(anchor[0] + dx, anchor[1] + dy)
            self.sleep(0.16)
            moved = self._read_near(box, origin, started, latest)
            vectors.append(((moved[0] - latest[0]) / 24.0, (moved[1] - latest[1]) / 24.0))
            self.game_input.move_cursor(*anchor)
            self.sleep(0.16)
            latest = self._read_near(box, origin, started, moved)
        return vectors[0], vectors[1], latest

    def _calibrate_keys(
        self,
        current: Coordinate,
        box: Box,
        origin: Coordinate,
        started: float,
    ) -> tuple[dict[str, tuple[float, float]], Coordinate]:
        vectors: dict[str, tuple[float, float]] = {}
        latest = current
        for key in ("W", "D"):
            self.game_input.tap_key(key, 0.06)
            self.sleep(0.24)
            moved = self._read_near(box, origin, started, latest)
            vectors[key] = (moved[0] - latest[0], moved[1] - latest[1])
            latest = moved
        vectors["S"] = (-vectors["W"][0], -vectors["W"][1])
        vectors["A"] = (-vectors["D"][0], -vectors["D"][1])
        if max(math.hypot(*value) for value in vectors.values()) < 0.5:
            raise RuntimeError("WASD calibration did not move the Palworld map")
        return vectors, latest

    def _best_key(
        self,
        error: tuple[float, float],
        vectors: dict[str, tuple[float, float]],
    ) -> tuple[str, float]:
        scores = {
            candidate: (
                error[0] * vectors[candidate][0] + error[1] * vectors[candidate][1]
            )
            / max(0.001, math.hypot(*vectors[candidate]))
            for candidate in vectors
        }
        key = max(scores, key=scores.get)
        if scores[key] <= 0:
            raise RuntimeError("Calibrated controls cannot move toward the target")
        vector = vectors[key]
        projection = max(
            0.15,
            (error[0] * vector[0] + error[1] * vector[1])
            / max(0.001, vector[0] ** 2 + vector[1] ** 2),
        )
        maximum_duration = 0.22 if math.hypot(*error) >= 100 else 0.16
        return key, min(maximum_duration, max(0.012, 0.06 * projection * 0.65))

    def _run(
        self,
        target: Coordinate,
        selection_box: Box,
        selection_point: Coordinate,
        confirm: bool,
        calibration_only: bool,
        add_button: Optional[Coordinate],
    ) -> None:
        started = time.monotonic()
        reused_calibration = False
        try:
            self.update_state(status="calibrating", message="Focusing Palworld and reading coordinates")
            if not self.game_input.focus_game():
                raise RuntimeError("Palworld window was not found or could not receive focus")
            self.game_input.move_cursor(*selection_point)
            self.sleep(0.3)
            current = self._read(selection_box, selection_point, started)
            self.update_state(
                status="calibrating",
                current=list(current),
                distanceMeters=distance_meters(current, target),
                message="Calibrating WASD with the cursor fixed at screen center",
            )
            if self._cached_key_vectors is not None and not calibration_only:
                key_vectors = dict(self._cached_key_vectors)
                reused_calibration = True
                self.update_state(message="Using validated WASD calibration")
            else:
                key_vectors, current = self._calibrate_keys(
                    current, selection_box, selection_point, started
                )
            calibration = {
                **{
                    key: [round(vector[0], 2), round(vector[1], 2)]
                    for key, vector in key_vectors.items()
                },
            }
            print(f"Game marker calibration: {calibration}", flush=True)
            if calibration_only:
                self._cached_key_vectors = dict(key_vectors)
                self.update_state(
                    active=False,
                    status="completed",
                    current=list(current),
                    distanceMeters=distance_meters(current, target),
                    calibration=calibration,
                    message="Calibration completed without movement or confirmation",
                )
                return
            stable = 0
            regressions = 0
            mouse_vectors: Optional[
                tuple[tuple[float, float], tuple[float, float]]
            ] = None
            for _attempt in range(180):
                self._check_safety(started)
                remaining = distance_meters(current, target)
                self.update_state(
                    status="moving",
                    current=list(current),
                    distanceMeters=remaining,
                    message=f"Moving to {target[0]}, {target[1]}",
                )
                if current == target:
                    stable += 1
                    if stable >= 2:
                        break
                    self.sleep(0.15)
                    current = self._read_near(
                        selection_box, selection_point, started, current, maximum_delta=2
                    )
                    continue
                stable = 0
                previous = current
                error = (float(target[0] - current[0]), float(target[1] - current[1]))
                action_key: Optional[str] = None
                action_duration = 0.0
                mouse_moved = False
                if math.hypot(*error) <= 12:
                    if mouse_vectors is None:
                        self.update_state(
                            status="moving",
                            current=list(current),
                            distanceMeters=remaining,
                            message="Calibrating mouse for the final adjustment",
                        )
                        mouse_x, mouse_y, current = self._calibrate_mouse(
                            current, selection_box, selection_point, started
                        )
                        mouse_vectors = (mouse_x, mouse_y)
                        calibration["mouseX"] = [
                            round(mouse_x[0], 4),
                            round(mouse_x[1], 4),
                        ]
                        calibration["mouseY"] = [
                            round(mouse_y[0], 4),
                            round(mouse_y[1], 4),
                        ]
                        continue
                    mouse_delta = solve_mouse_delta(error, *mouse_vectors)
                    if mouse_delta is not None:
                        step_x = round(max(-30.0, min(30.0, mouse_delta[0])))
                        step_y = round(max(-30.0, min(30.0, mouse_delta[1])))
                        if step_x or step_y:
                            cursor = self.game_input.cursor()
                            self.game_input.move_cursor(cursor[0] + step_x, cursor[1] + step_y)
                            self.sleep(0.16)
                            mouse_moved = True
                if not mouse_moved:
                    action_key, action_duration = self._best_key(error, key_vectors)
                    self.game_input.tap_key(action_key, action_duration)
                    self.sleep(0.18)
                current = self._read_near(selection_box, selection_point, started, previous)
                observed = (current[0] - previous[0], current[1] - previous[1])
                if action_key is not None and observed != (0, 0):
                    scale = 0.06 / action_duration
                    key_vectors[action_key] = (observed[0] * scale, observed[1] * scale)
                before = math.hypot(target[0] - previous[0], target[1] - previous[1])
                after = math.hypot(target[0] - current[0], target[1] - current[1])
                regressions = regressions + 1 if after > before + max(3.0, before * 0.03) else 0
                if regressions >= 3:
                    raise RuntimeError("Movement is diverging from the target; automation stopped")
            else:
                raise RuntimeError("Target coordinate was not reached within the movement limit")

            self._check_safety(started)
            if current != target:
                raise RuntimeError("Exact target validation failed")
            if confirm:
                if add_button is None:
                    raise RuntimeError("Add button position is not configured")
                self.update_state(
                    status="marking",
                    current=list(current),
                    distanceMeters=0,
                    message="Opening the marker dialog",
                )
                self.game_input.tap_key("E", 0.12)
                self.sleep(0.5)
                self._check_safety(started)
                self.update_state(message="Clicking Add")
                self.game_input.move_cursor(*add_button)
                self.sleep(0.06)
                self.game_input.left_click()
            self._cached_key_vectors = dict(key_vectors)
            self.update_state(
                active=False,
                status="completed",
                current=list(current),
                distanceMeters=0,
                message="Marker placed" if confirm else "Calibration completed",
                calibration=calibration,
            )
        except TimeoutError as exc:
            self.update_state(active=False, status="error", error=str(exc), message=str(exc))
        except RuntimeError as exc:
            status = "cancelled" if "cancelled" in str(exc).lower() else "error"
            self.update_state(active=False, status=status, error=str(exc), message=str(exc))
        except Exception as exc:
            if reused_calibration:
                self._cached_key_vectors = None
            message = str(exc) or exc.__class__.__name__
            self.update_state(active=False, status="error", error=message, message=message)
        finally:
            self.game_input.release_movement_keys()


class MouseComboLoop:
    """Focus Palworld, hold right mouse, click middle, repeat on an interval."""

    def __init__(
        self,
        update_state: StateUpdater,
        game_input: Optional[WindowsGameInput] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.update_state = update_state
        self.game_input = game_input or WindowsGameInput()
        self.sleep = sleep
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._interval = 40.0

    @property
    def active(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, interval_seconds: float) -> bool:
        if self.active:
            return False
        self._interval = max(1.0, float(interval_seconds))
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        self._cancel.set()
        try:
            self.game_input.right_button_up()
        except Exception:
            pass

    def _wait(self, seconds: float) -> None:
        deadline = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < deadline:
            if self._cancel.is_set() or self.game_input.escape_pressed():
                raise RuntimeError("Mouse combo loop cancelled")
            remaining = deadline - time.monotonic()
            self.sleep(min(0.2, max(0.05, remaining)))

    def _pulse(self) -> None:
        if not self.game_input.focus_game():
            raise RuntimeError("Palworld window was not found or could not receive focus")
        self.update_state(
            active=True,
            status="running",
            message="Holding right click and pressing middle click",
            error="",
        )
        self.game_input.right_button_down()
        try:
            self._wait(0.08)
            self.game_input.middle_click()
            self._wait(0.08)
        finally:
            self.game_input.right_button_up()

    def _run(self) -> None:
        finished = "idle"
        try:
            self.update_state(
                active=True,
                status="running",
                intervalSeconds=self._interval,
                message=f"Mouse combo loop every {self._interval:g}s · Esc to stop",
                error="",
            )
            while not self._cancel.is_set():
                self._pulse()
                self.update_state(
                    active=True,
                    status="waiting",
                    message=f"Waiting {self._interval:g}s · Esc to stop",
                    error="",
                )
                self._wait(self._interval)
            finished = "cancelled"
        except RuntimeError as exc:
            finished = "cancelled" if "cancelled" in str(exc).lower() else "error"
            self.update_state(active=False, status=finished, error=str(exc), message=str(exc))
            return
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            self.update_state(active=False, status="error", error=message, message=message)
            return
        finally:
            try:
                self.game_input.right_button_up()
            except Exception:
                pass
        if finished == "cancelled" or self._cancel.is_set():
            self.update_state(
                active=False,
                status="cancelled",
                message="Mouse combo loop stopped",
                error="",
            )
