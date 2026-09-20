from __future__ import annotations

import ctypes
import json
import math
import os
import threading
import time
from ctypes import wintypes
from pathlib import Path
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

CALIBRATION_CACHE_VERSION = 1
CALIBRATION_CACHE_PATH = (
    Path(__file__).resolve().parent.parent / ".cache" / "game-marker-calibration.json"
)

# Reversible optimization flags (env: 0/false/off disables; default on except timing).
def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no", "off")


OPT_ADAPTIVE_SLEEP = _env_flag("PALWORLD_MARKER_ADAPTIVE_SLEEP", "1")
OPT_DISK_CALIBRATION = _env_flag("PALWORLD_MARKER_DISK_CALIBRATION", "1")
OPT_MOUSE_CACHE = _env_flag("PALWORLD_MARKER_MOUSE_CACHE", "1")
OPT_DUAL_AXIS = _env_flag("PALWORLD_MARKER_DUAL_AXIS", "1")
OPT_ADAPTIVE_CONFIRM = _env_flag("PALWORLD_MARKER_ADAPTIVE_CONFIRM", "1")
MARKER_TIMING = _env_flag("PALWORLD_MARKER_TIMING", "0")

NEAR_FIELD = 12.0
STABLE_NEAR_FIELD = 25.0
MOUSE_VALIDATE_PIXELS = 24
MOUSE_VALIDATE_ALIGNMENT = 0.35
DUAL_AXIS_MIN_ERROR = 60.0


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


def monitor_cache_key() -> str:
    try:
        user32 = ctypes.windll.user32
        return f"{int(user32.GetSystemMetrics(0))}x{int(user32.GetSystemMetrics(1))}"
    except Exception:
        return "unknown"


class RunTiming:
    """Optional per-run timing; enabled via PALWORLD_MARKER_TIMING=1."""

    def __init__(self) -> None:
        self.enabled = MARKER_TIMING
        self.phase_ms: dict[str, float] = {}
        self.sleep_ms: dict[str, float] = {}
        self.ocr_reads = 0
        self.loop_iterations = 0
        self._phase_started: dict[str, float] = {}
        self._sleep_phase = "other"

    def begin_phase(self, name: str) -> None:
        if not self.enabled:
            return
        self._phase_started[name] = time.perf_counter()
        self._sleep_phase = name

    def end_phase(self, name: str) -> None:
        if not self.enabled:
            return
        started = self._phase_started.pop(name, None)
        if started is None:
            return
        self.phase_ms[name] = self.phase_ms.get(name, 0.0) + (time.perf_counter() - started) * 1000.0
        self._sleep_phase = "other"

    def add_sleep(self, seconds: float) -> None:
        if not self.enabled:
            return
        phase = self._sleep_phase
        self.sleep_ms[phase] = self.sleep_ms.get(phase, 0.0) + seconds * 1000.0

    def record_ocr(self) -> None:
        if self.enabled:
            self.ocr_reads += 1

    def record_iteration(self) -> None:
        if self.enabled:
            self.loop_iterations += 1

    def log(self, prefix: str = "marker-timing") -> None:
        if not self.enabled:
            return
        total = sum(self.phase_ms.values())
        print(
            f"[{prefix}] phases_ms={{{', '.join(f'{k}={v:.1f}' for k, v in sorted(self.phase_ms.items()))}}}"
            f" sleep_ms={{{', '.join(f'{k}={v:.1f}' for k, v in sorted(self.sleep_ms.items()))}}}"
            f" ocr_reads={self.ocr_reads} loop_iters={self.loop_iterations} total_phase_ms={total:.1f}",
            flush=True,
        )


def load_calibration_cache() -> dict:
    try:
        if not CALIBRATION_CACHE_PATH.is_file():
            return {"version": CALIBRATION_CACHE_VERSION, "monitors": {}}
        data = json.loads(CALIBRATION_CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or int(data.get("version") or 0) != CALIBRATION_CACHE_VERSION:
            return {"version": CALIBRATION_CACHE_VERSION, "monitors": {}}
        monitors = data.get("monitors")
        if not isinstance(monitors, dict):
            monitors = {}
        return {"version": CALIBRATION_CACHE_VERSION, "monitors": monitors}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {"version": CALIBRATION_CACHE_VERSION, "monitors": {}}


def save_calibration_cache(payload: dict) -> None:
    try:
        CALIBRATION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CALIBRATION_CACHE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(CALIBRATION_CACHE_PATH)
    except OSError:
        pass


def invalidate_calibration_cache(monitor_key: Optional[str] = None) -> None:
    data = load_calibration_cache()
    if monitor_key is None:
        data["monitors"] = {}
    else:
        data["monitors"].pop(monitor_key, None)
    save_calibration_cache(data)


def _vectors_from_cache(entry: dict) -> Optional[dict[str, tuple[float, float]]]:
    keys = entry.get("keys")
    if not isinstance(keys, dict):
        return None
    vectors: dict[str, tuple[float, float]] = {}
    for name in ("W", "A", "S", "D"):
        raw = keys.get(name)
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            return None
        vectors[name] = (float(raw[0]), float(raw[1]))
    return vectors


def _mouse_from_cache(
    entry: dict,
) -> Optional[tuple[tuple[float, float], tuple[float, float]]]:
    mx = entry.get("mouseX")
    my = entry.get("mouseY")
    if not isinstance(mx, (list, tuple)) or not isinstance(my, (list, tuple)):
        return None
    if len(mx) != 2 or len(my) != 2:
        return None
    return (float(mx[0]), float(mx[1])), (float(my[0]), float(my[1]))


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
        self.tap_keys([key], duration)

    def tap_keys(self, keys: list[str], duration: float) -> None:
        codes = [VK[key] for key in keys]
        for code in codes:
            self.user32.keybd_event(code, 0, 0, 0)
        try:
            time.sleep(duration)
        finally:
            for code in codes:
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
        cache_key: Optional[str] = None,
    ) -> None:
        self.read_coordinate = read_coordinate
        self.update_state = update_state
        self.game_input = game_input or WindowsGameInput()
        self.timeout_seconds = timeout_seconds
        self._sleep_impl = sleep
        self._cache_key = cache_key or monitor_cache_key()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cached_key_vectors: Optional[dict[str, tuple[float, float]]] = None
        self._cached_mouse_vectors: Optional[
            tuple[tuple[float, float], tuple[float, float]]
        ] = None
        self.timing = RunTiming()

    def sleep(self, seconds: float) -> None:
        self.timing.add_sleep(seconds)
        self._sleep_impl(seconds)

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
        self.timing = RunTiming()
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

    def _ocr(self, box: Box, origin: Coordinate) -> Optional[Coordinate]:
        self.timing.record_ocr()
        return self.read_coordinate(self._translated_box(box, origin))

    def _wait_settle(
        self,
        box: Box,
        origin: Coordinate,
        started: float,
        previous: Coordinate,
        max_wait: float,
        poll: float = 0.05,
    ) -> Coordinate:
        """Adaptive wait: poll until two equal OCR reads, capped by max_wait."""
        if not OPT_ADAPTIVE_SLEEP or max_wait <= 0:
            self.sleep(max_wait)
            return previous
        attempts = max(2, int(math.ceil(max_wait / poll)))
        last: Optional[Coordinate] = None
        streak = 0
        for _ in range(attempts):
            self._check_safety(started)
            value = self._ocr(box, origin)
            if value is not None:
                streak = streak + 1 if value == last else 1
                last = value
                if streak >= 2:
                    return value
            self.sleep(poll)
        if last is not None:
            return last
        return previous

    def _read_after_action(
        self,
        box: Box,
        origin: Coordinate,
        started: float,
        previous: Coordinate,
        max_wait: float,
        require_stable: bool = True,
        maximum_delta: float = 200.0,
        poll: float = 0.05,
    ) -> Coordinate:
        """Wait for the map to settle and return the post-action coordinate."""
        if not OPT_ADAPTIVE_SLEEP:
            self.sleep(max_wait)
            return self._read_near(
                box,
                origin,
                started,
                previous,
                maximum_delta=maximum_delta,
                require_stable=require_stable,
            )
        needed = 2
        attempts = max(needed + 1, int(math.ceil(max_wait / poll)))
        last: Optional[Coordinate] = None
        streak = 0
        for _ in range(attempts):
            self._check_safety(started)
            value = self._ocr(box, origin)
            if value is not None and math.hypot(
                value[0] - previous[0], value[1] - previous[1]
            ) <= maximum_delta:
                streak = streak + 1 if value == last else 1
                last = value
                if streak >= needed:
                    return value
            self.sleep(poll)
        return self._read_near(
            box,
            origin,
            started,
            previous,
            maximum_delta=maximum_delta,
            require_stable=True,
        )

    def _read(
        self,
        box: Box,
        origin: Coordinate,
        started: float,
        require_stable: bool = True,
    ) -> Coordinate:
        needed = 2
        previous: Optional[Coordinate] = None
        consecutive = 0
        for _attempt in range(6):
            self._check_safety(started)
            value = self._ocr(box, origin)
            if value is not None:
                consecutive = consecutive + 1 if value == previous else 1
                previous = value
                if consecutive >= needed:
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
        require_stable: bool = True,
    ) -> Coordinate:
        for _attempt in range(3):
            value = self._read(box, origin, started, require_stable=require_stable)
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
            moved = self._read_after_action(
                box, origin, started, latest, 0.16, require_stable=True
            )
            vectors.append(((moved[0] - latest[0]) / 24.0, (moved[1] - latest[1]) / 24.0))
            self.game_input.move_cursor(*anchor)
            latest = self._read_after_action(
                box, origin, started, moved, 0.16, require_stable=True
            )
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
            moved = self._read_after_action(
                box, origin, started, latest, 0.24, require_stable=True
            )
            vectors[key] = (moved[0] - latest[0], moved[1] - latest[1])
            latest = moved
        vectors["S"] = (-vectors["W"][0], -vectors["W"][1])
        vectors["A"] = (-vectors["D"][0], -vectors["D"][1])
        if max(math.hypot(*value) for value in vectors.values()) < 0.5:
            raise RuntimeError("WASD calibration did not move the Palworld map")
        return vectors, latest

    def _validate_cached_keys(
        self,
        vectors: dict[str, tuple[float, float]],
        current: Coordinate,
        box: Box,
        origin: Coordinate,
        started: float,
    ) -> tuple[bool, Coordinate]:
        expected = vectors.get("W")
        if expected is None or math.hypot(*expected) < 0.5:
            return False, current
        self.game_input.tap_key("W", 0.06)
        moved = self._read_after_action(
            box, origin, started, current, 0.24, require_stable=True
        )
        observed = (moved[0] - current[0], moved[1] - current[1])
        if math.hypot(*observed) < 0.5:
            return False, moved
        alignment = (
            observed[0] * expected[0] + observed[1] * expected[1]
        ) / (math.hypot(*observed) * math.hypot(*expected))
        return alignment > 0.35, moved

    def _validate_cached_mouse(
        self,
        mouse_vectors: tuple[tuple[float, float], tuple[float, float]],
        current: Coordinate,
        box: Box,
        origin: Coordinate,
        started: float,
    ) -> tuple[bool, Coordinate]:
        mouse_x, _mouse_y = mouse_vectors
        if math.hypot(*mouse_x) < 1e-6:
            return False, current
        anchor = self.game_input.cursor()
        pixels = MOUSE_VALIDATE_PIXELS
        self.game_input.move_cursor(anchor[0] + pixels, anchor[1])
        moved = self._read_after_action(
            box, origin, started, current, 0.16, require_stable=True
        )
        observed = (moved[0] - current[0], moved[1] - current[1])
        expected = (mouse_x[0] * pixels, mouse_x[1] * pixels)
        self.game_input.move_cursor(*anchor)
        restored = self._read_after_action(
            box, origin, started, moved, 0.16, require_stable=True
        )
        if math.hypot(*observed) < 0.5 or math.hypot(*expected) < 0.5:
            return False, restored
        alignment = (
            observed[0] * expected[0] + observed[1] * expected[1]
        ) / (math.hypot(*observed) * math.hypot(*expected))
        return alignment >= MOUSE_VALIDATE_ALIGNMENT, restored

    def _discard_mouse_cache(self) -> None:
        self._cached_mouse_vectors = None
        if not OPT_DISK_CALIBRATION:
            return
        data = load_calibration_cache()
        entry = data["monitors"].get(self._cache_key)
        if isinstance(entry, dict):
            entry.pop("mouseX", None)
            entry.pop("mouseY", None)
            data["monitors"][self._cache_key] = entry
            save_calibration_cache(data)

    def _load_disk_calibration(
        self,
    ) -> tuple[
        Optional[dict[str, tuple[float, float]]],
        Optional[tuple[tuple[float, float], tuple[float, float]]],
    ]:
        if not OPT_DISK_CALIBRATION:
            return None, None
        entry = load_calibration_cache()["monitors"].get(self._cache_key)
        if not isinstance(entry, dict):
            return None, None
        keys = _vectors_from_cache(entry)
        mouse = _mouse_from_cache(entry) if OPT_MOUSE_CACHE else None
        return keys, mouse

    def _persist_disk_calibration(
        self,
        key_vectors: dict[str, tuple[float, float]],
        mouse_vectors: Optional[tuple[tuple[float, float], tuple[float, float]]],
    ) -> None:
        if not OPT_DISK_CALIBRATION:
            return
        data = load_calibration_cache()
        entry: dict = {
            "keys": {name: [round(v[0], 4), round(v[1], 4)] for name, v in key_vectors.items()},
        }
        if mouse_vectors is not None and OPT_MOUSE_CACHE:
            entry["mouseX"] = [round(mouse_vectors[0][0], 6), round(mouse_vectors[0][1], 6)]
            entry["mouseY"] = [round(mouse_vectors[1][0], 6), round(mouse_vectors[1][1], 6)]
        data["monitors"][self._cache_key] = entry
        save_calibration_cache(data)

    def _invalidate_caches(self) -> None:
        self._cached_key_vectors = None
        self._cached_mouse_vectors = None
        if OPT_DISK_CALIBRATION:
            invalidate_calibration_cache(self._cache_key)

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
        distance = math.hypot(*error)
        if distance >= 150 and OPT_DUAL_AXIS:
            maximum_duration = 0.32
        elif distance >= 100:
            maximum_duration = 0.22
        else:
            maximum_duration = 0.16
        return key, min(maximum_duration, max(0.012, 0.06 * projection * 0.65))

    def _plan_key_move(
        self,
        error: tuple[float, float],
        vectors: dict[str, tuple[float, float]],
    ) -> tuple[list[str], float]:
        if not OPT_DUAL_AXIS:
            key, duration = self._best_key(error, vectors)
            return [key], duration

        def score(candidate: str) -> float:
            return (
                error[0] * vectors[candidate][0] + error[1] * vectors[candidate][1]
            ) / max(0.001, math.hypot(*vectors[candidate]))

        ns = max(("W", "S"), key=score)
        ew = max(("A", "D"), key=score)
        keys: list[str] = []
        if score(ns) > 0:
            keys.append(ns)
        if score(ew) > 0:
            keys.append(ew)
        if not keys:
            raise RuntimeError("Calibrated controls cannot move toward the target")
        if len(keys) == 1:
            key, duration = self._best_key(error, vectors)
            return [key], duration
        durations = [self._best_key(error, {k: vectors[k]})[1] for k in keys]
        return keys, max(durations)

    def _wait_confirm_dialog(self, add_button: Coordinate, started: float) -> None:
        max_wait = 0.5
        if not OPT_ADAPTIVE_CONFIRM:
            self.sleep(max_wait)
            return
        min_wait = 0.12
        self.sleep(min_wait)
        # Unit tests inject a no-op sleep; skip pixel polling there.
        if self._sleep_impl is not time.sleep:
            return
        try:
            from PIL import ImageGrab
        except ImportError:
            self.sleep(max(0.0, max_wait - min_wait))
            return
        x, y = add_button
        box = (max(0, x - 24), max(0, y - 14), x + 24, y + 14)
        try:
            baseline = ImageGrab.grab(bbox=box, all_screens=True).tobytes()
        except Exception:
            self.sleep(max(0.0, max_wait - min_wait))
            return
        attempts = max(1, int(math.ceil((max_wait - min_wait) / 0.05)))
        for _ in range(attempts):
            self._check_safety(started)
            try:
                sample = ImageGrab.grab(bbox=box, all_screens=True).tobytes()
            except Exception:
                break
            if sample != baseline:
                return
            self.sleep(0.05)

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
        mouse_vectors: Optional[tuple[tuple[float, float], tuple[float, float]]] = None
        try:
            self.update_state(status="calibrating", message="Focusing Palworld and reading coordinates")
            self.timing.begin_phase("focus")
            if not self.game_input.focus_game():
                raise RuntimeError("Palworld window was not found or could not receive focus")
            self.game_input.move_cursor(*selection_point)
            self.sleep(0.3)
            self.timing.end_phase("focus")

            self.timing.begin_phase("initial_read")
            current = self._read(selection_box, selection_point, started, require_stable=True)
            self.timing.end_phase("initial_read")
            self.update_state(
                status="calibrating",
                current=list(current),
                distanceMeters=distance_meters(current, target),
                message="Calibrating WASD with the cursor fixed at screen center",
            )

            self.timing.begin_phase("calibration")
            key_vectors: Optional[dict[str, tuple[float, float]]] = None
            if self._cached_key_vectors is not None and not calibration_only:
                key_vectors = dict(self._cached_key_vectors)
                reused_calibration = True
                if self._cached_mouse_vectors is not None and OPT_MOUSE_CACHE:
                    ok_mouse, current = self._validate_cached_mouse(
                        self._cached_mouse_vectors,
                        current,
                        selection_box,
                        selection_point,
                        started,
                    )
                    if ok_mouse:
                        mouse_vectors = self._cached_mouse_vectors
                    else:
                        self._discard_mouse_cache()
                self.update_state(message="Using validated WASD calibration")
            elif not calibration_only:
                disk_keys, disk_mouse = self._load_disk_calibration()
                if disk_keys is not None:
                    ok, current = self._validate_cached_keys(
                        disk_keys, current, selection_box, selection_point, started
                    )
                    if ok:
                        key_vectors = dict(disk_keys)
                        reused_calibration = True
                        if disk_mouse is not None and OPT_MOUSE_CACHE:
                            ok_mouse, current = self._validate_cached_mouse(
                                disk_mouse,
                                current,
                                selection_box,
                                selection_point,
                                started,
                            )
                            if ok_mouse:
                                mouse_vectors = disk_mouse
                            else:
                                self._discard_mouse_cache()
                        self.update_state(message="Using disk WASD calibration")
                    else:
                        invalidate_calibration_cache(self._cache_key)

            if key_vectors is None:
                key_vectors, current = self._calibrate_keys(
                    current, selection_box, selection_point, started
                )
            self.timing.end_phase("calibration")

            calibration = {
                **{
                    key: [round(vector[0], 2), round(vector[1], 2)]
                    for key, vector in key_vectors.items()
                },
            }
            print(f"Game marker calibration: {calibration}", flush=True)
            if calibration_only:
                self._cached_key_vectors = dict(key_vectors)
                self._persist_disk_calibration(key_vectors, None)
                self.update_state(
                    active=False,
                    status="completed",
                    current=list(current),
                    distanceMeters=distance_meters(current, target),
                    calibration=calibration,
                    message="Calibration completed without movement or confirmation",
                )
                self.timing.log()
                return

            stable = 0
            regressions = 0
            self.timing.begin_phase("loop")
            for _attempt in range(180):
                self.timing.record_iteration()
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
                        selection_box,
                        selection_point,
                        started,
                        current,
                        maximum_delta=2,
                        require_stable=True,
                    )
                    continue
                stable = 0
                previous = current
                error = (float(target[0] - current[0]), float(target[1] - current[1]))
                action_keys: list[str] = []
                action_duration = 0.0
                mouse_moved = False
                if math.hypot(*error) <= NEAR_FIELD:
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
                            mouse_moved = True
                if not mouse_moved:
                    action_keys, action_duration = self._plan_key_move(error, key_vectors)
                    if hasattr(self.game_input, "tap_keys"):
                        self.game_input.tap_keys(action_keys, action_duration)
                    else:
                        for key in action_keys:
                            self.game_input.tap_key(key, action_duration)
                settle_budget = 0.16 if mouse_moved else 0.18
                current = self._read_after_action(
                    selection_box,
                    selection_point,
                    started,
                    previous,
                    settle_budget,
                    require_stable=True,
                )
                observed = (current[0] - previous[0], current[1] - previous[1])
                if action_keys and observed != (0, 0) and action_duration > 0:
                    scale = 0.06 / action_duration
                    if len(action_keys) == 1:
                        key_vectors[action_keys[0]] = (
                            observed[0] * scale,
                            observed[1] * scale,
                        )
                    else:
                        for key in action_keys:
                            expected = key_vectors[key]
                            share = abs(
                                observed[0] * expected[0] + observed[1] * expected[1]
                            ) / max(0.001, math.hypot(*expected) * math.hypot(*observed))
                            key_vectors[key] = (
                                expected[0] * (0.7 + 0.3 * share),
                                expected[1] * (0.7 + 0.3 * share),
                            )
                before = math.hypot(target[0] - previous[0], target[1] - previous[1])
                after = math.hypot(target[0] - current[0], target[1] - current[1])
                regressions = regressions + 1 if after > before + max(3.0, before * 0.03) else 0
                if regressions >= 3:
                    raise RuntimeError("Movement is diverging from the target; automation stopped")
            else:
                raise RuntimeError("Target coordinate was not reached within the movement limit")
            self.timing.end_phase("loop")

            self._check_safety(started)
            if current != target:
                raise RuntimeError("Exact target validation failed")
            if confirm:
                if add_button is None:
                    raise RuntimeError("Add button position is not configured")
                self.timing.begin_phase("confirm")
                self.update_state(
                    status="marking",
                    current=list(current),
                    distanceMeters=0,
                    message="Opening the marker dialog",
                )
                self.game_input.tap_key("E", 0.12)
                self._wait_confirm_dialog(add_button, started)
                self._check_safety(started)
                self.update_state(message="Clicking Add")
                self.game_input.move_cursor(*add_button)
                self.sleep(0.06)
                self.game_input.left_click()
                self.timing.end_phase("confirm")
            self._cached_key_vectors = dict(key_vectors)
            if mouse_vectors is not None:
                self._cached_mouse_vectors = mouse_vectors
            self._persist_disk_calibration(key_vectors, mouse_vectors)
            self.update_state(
                active=False,
                status="completed",
                current=list(current),
                distanceMeters=0,
                message="Marker placed" if confirm else "Calibration completed",
                calibration=calibration,
            )
            self.timing.log()
        except TimeoutError as exc:
            self.update_state(active=False, status="error", error=str(exc), message=str(exc))
            self.timing.log()
        except RuntimeError as exc:
            status = "cancelled" if "cancelled" in str(exc).lower() else "error"
            self.update_state(active=False, status=status, error=str(exc), message=str(exc))
            self.timing.log()
        except Exception as exc:
            if reused_calibration:
                self._invalidate_caches()
            else:
                self._cached_key_vectors = None
                self._cached_mouse_vectors = None
            message = str(exc) or exc.__class__.__name__
            self.update_state(active=False, status="error", error=message, message=message)
            self.timing.log()
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
