"""
Fixed coordinate tooltip for the map HUD, integrated with the Vue application.
Usage: py -3 run.py  (or py -3 -m server.coord_tooltip / start.bat)
"""
from __future__ import annotations

import ctypes
import hashlib
import io
import json
import mimetypes
import os
import signal
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from collections import OrderedDict
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image, ImageFilter, ImageGrab, ImageOps
from .autoloop import DEFAULT_INPUT_DELAY, DEFAULT_WAITS, WAIT_KEYS, AutoLoop, AutoLoopError
from .game_marker_automation import GameMarkerController, MouseComboLoop, WindowsGameInput
from .marker_timing import (
    MARKER_TIMING,
    _current_timing_collector,
    current_ocr_context,
    record_ocr_meta,
)
from .player_position import read_palworld_position

PORT = int(os.environ.get("PALWORLD_PORT", "8765"))
VERSION = "tooltip-v20-game-marker"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_ROOT = PROJECT_ROOT / "dist"
PROGRESS_PATH = PROJECT_ROOT / ".local" / "progress.json"
LEGACY_PROGRESS_PATH = PROJECT_ROOT / "progress.json"
PROGRESS_LOCK = threading.RLock()  # reentrante: save lê o estado atual dentro do lock

# Fast-path: skip white-mask fallback when focused crops already agree.
OCR_EARLY_EXIT_VOTES = 2
OCR_EARLY_EXIT_MIN_CONF = 0.85
OCR_FAST_MAX_VARIANTS = 5
OCR_FAST_CROP_ORDER = (7, 6, 8, 5, 9, 2, 12)  # center-first in 5x3 grid

CHECK_KEYS = (
    "alphas",
    "bounties",
    "effigies",
    "dungeons",
    "towers",
    "journals",
    "oilrigs",
    "camps",
    "collectibles",
    "travel",
)

# MapGenie Palpagos 1.0, pyramid z8-z16
# OFFLINE MODE: tiles served from local cache only (.cache/map-tiles/)
# Run tools/download_map_tiles.py to populate the cache.
MAPGENIE_TILE_BASE = "https://tiles.mapgenie.io/games/palworld/1-0/default-v1"
MAPGENIE_MIN_Z = 8
MAPGENIE_MAX_Z = 16
TILE_DISK = PROJECT_ROOT / ".cache" / "map-tiles"

# MapGenie World Tree, pyramid z8-z14
# OFFLINE MODE: tiles served from local cache only (.cache/map-tiles-wt/)
MAPGENIE_WT_TILE_BASE = "https://tiles.mapgenie.io/games/palworld/world-tree/default-v1"
MAPGENIE_WT_MIN_Z = 8
MAPGENIE_WT_MAX_Z = 14
WT_TILE_DISK = PROJECT_ROOT / ".cache" / "map-tiles-wt"
ICON_DISK = PROJECT_ROOT / ".cache" / "map-icons"
BUNDLED_ICON_DISK = Path(__file__).resolve().parent / "static" / "map-icons"
ICON_ALLOWED_HOSTS = {"cdn.paldb.cc"}

# ── Quem pode falar com o helper ────────────────────────────────────────────
# O helper expõe automação de mouse/teclado (e o progresso) em 127.0.0.1.
# Sem restrição, qualquer página aberta no navegador do usuário poderia fazer
# fetch para cá: um POST simples (text/plain) não gera preflight, então o
# navegador entrega o corpo sem perguntar. O hostname é o que fecha o vetor
# (ataque remoto e DNS rebinding nunca chegam com Host/Origin local).
ALLOWED_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

# Corpos de POST limitados (o maior caso de uso é o payload de progresso).
MAX_POST_BYTES = 4 * 1024 * 1024


def _origin_is_local(origin: str) -> bool:
    """`Origin` vazio = cliente não-navegador (curl/urllib/run.py) → permite.

    Um ataque vindo de página web sempre carrega `Origin`, então recusar
    qualquer host que não seja a própria máquina fecha o vetor.
    """
    origin = (origin or "").strip()
    if not origin:
        return True
    parsed = urlparse(origin)
    if parsed.scheme not in ("http", "https"):
        return False
    return (parsed.hostname or "") in ALLOWED_LOCAL_HOSTS


def _host_is_local(host: str) -> bool:
    """Guarda contra DNS rebinding: o `Host` precisa apontar para esta máquina."""
    host = (host or "").strip().lower()
    if host.startswith("["):  # IPv6 literal: [::1]:8765
        end = host.find("]")
        host = host[1:end] if end != -1 else host
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host in ALLOWED_LOCAL_HOSTS
TILE_BYTES_CACHE: OrderedDict[Tuple[str, int, int, int], bytes] = OrderedDict()
ICON_BYTES_CACHE: OrderedDict[str, bytes] = OrderedDict()
TILE_CACHE_MAX_BYTES = 32 * 1024 * 1024
ICON_CACHE_MAX_BYTES = 8 * 1024 * 1024
_IMAGE_CACHE_LOCK = threading.Lock()
_TILE_FETCH_LOCK = threading.Semaphore(4)
_TILE_FETCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

state_lock = threading.Lock()
state = {"active": False, "x": 0, "y": 0, "label": ""}
ocr_lock = threading.Lock()
ocr_state = {"active": False, "status": "idle", "text": "", "error": ""}
game_marker_lock = threading.Lock()
game_marker_state = {
    "active": False,
    "status": "idle",
    "target": None,
    "current": None,
    "distanceMeters": None,
    "calibration": None,
    "message": "",
    "error": "",
}
overlay: Optional["HudTooltip"] = None
ocr_selector: Optional["OcrSelector"] = None
game_marker_controller: Optional[GameMarkerController] = None
mouse_loop_lock = threading.Lock()
mouse_loop_state = {
    "active": False,
    "status": "idle",
    "intervalSeconds": 40.0,
    "message": "",
    "error": "",
}
mouse_loop_controller: Optional[MouseComboLoop] = None
autoloop_controller: Optional[AutoLoop] = None


def update_game_marker_state(**changes) -> None:
    collector = _current_timing_collector()
    t0 = time.perf_counter()
    game_marker_lock.acquire()
    wait_ms = (time.perf_counter() - t0) * 1000.0
    try:
        if collector is not None and wait_ms >= 0.05:
            collector.add_lock("game_marker_lock", wait_ms)
        game_marker_state.update(changes)
    finally:
        game_marker_lock.release()


def update_mouse_loop_state(**changes) -> None:
    with mouse_loop_lock:
        mouse_loop_state.update(changes)


def read_game_coordinate(bbox: Tuple[int, int, int, int]) -> Optional[Tuple[int, int]]:
    if ocr_selector is None:
        return None
    try:
        value = ocr_selector.recognize_bbox(bbox, save_debug=True, fast=True)
        first, second = value.split(",", 1)
        return int(first.strip()), int(second.strip())
    except (RuntimeError, TypeError, ValueError):
        return None


def player_ingame_coordinate() -> Optional[Tuple[int, int]]:
    """Player position in in-game map units (same conversion as toIngamePoint in the frontend)."""
    state = read_palworld_position()
    position = state.get("position") if state.get("status") == "ready" else None
    if not position:
        return None
    return (
        round((position["gameY"] - 158_000) / 459),
        round((position["gameX"] + 123_888) / 459),
    )


def game_screen_center() -> Tuple[int, int]:
    left, top, width, height = largest_monitor()
    return left + width // 2, top + height // 2


def game_coordinate_box() -> Tuple[int, int, int, int]:
    left, top, width, height = largest_monitor()
    center_x = left + round(width * 0.142)
    center_y = top + round(height * 0.153)
    box_width = max(160, round(width * 0.07))
    box_height = max(40, round(height * 0.03))
    return (
        center_x - box_width // 2,
        center_y - box_height // 2,
        center_x + box_width // 2,
        center_y + box_height // 2,
    )


def game_marker_add_button() -> Tuple[int, int]:
    left, top, width, height = largest_monitor()
    return left + round(width * 0.5), top + round(height * 0.808)


def begin_game_marker_after_selection(
    target: Tuple[int, int],
    confirm: bool,
    calibration_only: bool,
    bbox: Tuple[int, int, int, int],
    point: Tuple[int, int],
) -> None:
    if game_marker_controller is None:
        update_game_marker_state(
            active=False,
            status="error",
            message="Game marker automation is unavailable",
            error="Game marker automation is unavailable",
        )
        return
    update_game_marker_state(
        active=True,
        status="calibrating",
        message="Restoring Palworld focus",
        error="",
    )
    if not game_marker_controller.start(
        target,
        bbox,
        point,
        confirm,
        calibration_only,
        game_marker_add_button(),
    ):
        update_game_marker_state(
            active=False,
            status="error",
            message="Game marker automation is already active",
            error="Game marker automation is already active",
        )


def load_progress_file() -> dict:
    with PROGRESS_LOCK:
        source = PROGRESS_PATH if PROGRESS_PATH.is_file() else LEGACY_PROGRESS_PATH
        if not source.is_file():
            return {
                "version": 1,
                "revision": 0,
                "checks": {key: {} for key in CHECK_KEYS},
                "breedOwned": {},
                "prefs": {},
                "updatedAt": "",
            }
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
        prefs = data.get("prefs") if isinstance(data.get("prefs"), dict) else {}
        cake = data.get("cake") if isinstance(data.get("cake"), dict) else None
        result = {
            "version": int(data.get("version") or 1),
            "revision": max(0, int(data.get("revision") or 0)),
            "checks": {
                key: checks.get(key) if isinstance(checks.get(key), dict) else {}
                for key in CHECK_KEYS
            },
            "breedOwned": data.get("breedOwned") if isinstance(data.get("breedOwned"), dict) else {},
            "prefs": prefs,
            "updatedAt": str(data.get("updatedAt") or ""),
        }
        if cake is not None:
            result["cake"] = cake
        return result


def save_progress_file(body: dict) -> dict:
    progress_in = body.get("progress")
    base_revision = body.get("baseRevision")
    if (
        not isinstance(progress_in, dict)
        or not isinstance(base_revision, int)
        or isinstance(base_revision, bool)
        or base_revision < 0
    ):
        return {"invalid": True}

    checks_in = progress_in.get("checks")
    prefs_in = progress_in.get("prefs")
    owned_in = progress_in.get("breedOwned")
    if (
        not isinstance(checks_in, dict)
        or any(not isinstance(checks_in.get(key), dict) for key in CHECK_KEYS)
        or not isinstance(prefs_in, dict)
        or not isinstance(owned_in, dict)
    ):
        return {"invalid": True}
    cake_in = progress_in.get("cake") if isinstance(progress_in.get("cake"), dict) else None
    checks: dict = {}
    for key in CHECK_KEYS:
        raw = checks_in.get(key)
        if not isinstance(raw, dict):
            checks[key] = {}
            continue
        checks[key] = {str(k): True for k, v in raw.items() if v}
    breed_owned = {str(k): True for k, v in owned_in.items() if v}
    payload = {
        "version": max(1, int(progress_in.get("version") or 1)),
        "revision": max(0, int(progress_in.get("revision") or 0)),
        "updatedAt": progress_in.get("updatedAt") or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": checks,
        "breedOwned": breed_owned,
        "prefs": prefs_in,
    }
    with PROGRESS_LOCK:
        stored = load_progress_file()
        stored_revision = int(stored.get("revision") or 0)
        if base_revision != stored_revision:
            return {"conflict": True, "progress": stored}
        payload["revision"] = stored_revision + 1
        if cake_in is None and isinstance(stored.get("cake"), dict):
            payload["cake"] = stored["cake"]
        PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PROGRESS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(PROGRESS_PATH)
    return {
        "ok": True,
        "progress": payload,
    }
if hasattr(ctypes, "WINFUNCTYPE"):
    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(wintypes.RECT),
        ctypes.c_longlong,
    )
else:
    MonitorEnumProc = None


class HudTooltip:
    """Fixed tooltip near the upper-left corner of the map panel."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.92)
        bg = "#1a222c"
        border = "#3ecf8e"
        self.win.configure(bg=border)
        inner = tk.Frame(self.win, bg=bg, padx=10, pady=6)
        inner.pack(padx=1, pady=1)
        self.label = tk.Label(
            inner,
            text="",
            fg=border,
            bg=bg,
            font=("Consolas", 14, "bold"),
            justify="left",
        )
        self.label.pack()
        self._active = False
        self.win.withdraw()
        self._place_xy = hud_anchor_xy()
        self.win.bind("<Escape>", lambda _e: self.hide())
        self.root.bind_all("<Escape>", lambda _e: self.hide())
        print(
            f"HUD anchor @ ({self._place_xy[0]}, {self._place_xy[1]})",
            flush=True,
        )

    def show(self, x: int, y: int, label: str = "") -> None:
        lines = [f"({x}, {y})"]
        if label:
            lines.append(label)
        self.label.config(text="\n".join(lines))
        self._active = True
        px, py = self._place_xy
        self.win.geometry(f"+{px}+{py}")
        self.win.deiconify()

    def hide(self) -> None:
        self._active = False
        self.win.withdraw()
        with state_lock:
            state.update(active=False, x=0, y=0, label="")
        print("Tooltip OFF (Esc/hide)", flush=True)

    def run(self) -> None:
        def request_quit(*_args) -> None:
            try:
                self.root.after(0, self.root.quit)
            except Exception:
                pass

        try:
            signal.signal(signal.SIGINT, request_quit)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, request_quit)
        except Exception:
            pass

        def pump() -> None:
            self.root.after(200, pump)

        pump()
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            request_quit()


class OcrSelector:
    """Select a 10% x 5% screen area and copy recognized coordinates."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.24)
        self.win.configure(bg="#05080c")
        self.canvas = tk.Canvas(
            self.win,
            bg="#05080c",
            cursor="crosshair",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.monitor = (0, 0, 1, 1)
        self.rect_w = 180
        self.rect_h = 44
        self.pointer = (0, 0)
        self._ocr_engine = None
        self._ocr_direct_engine = None
        self._recognition_lock = threading.Lock()
        self._selection_callback: Optional[
            Callable[[Tuple[int, int, int, int], Tuple[int, int]], None]
        ] = None
        self._instruction = "Click to read · Esc to cancel"
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Button-3>", lambda _e: self.cancel())
        self.win.bind("<Escape>", lambda _e: self.cancel())

    def activate(
        self,
        callback: Optional[
            Callable[[Tuple[int, int, int, int], Tuple[int, int]], None]
        ] = None,
        instruction: str = "Click to read · Esc to cancel",
    ) -> None:
        self._selection_callback = callback
        self._instruction = instruction
        ml, mt, mw, mh = largest_monitor()
        self.monitor = (ml, mt, mw, mh)
        self.rect_w = max(160, int(mw * 0.07))
        self.rect_h = max(40, int(mh * 0.03))
        self.win.geometry(f"{mw}x{mh}+{ml}+{mt}")
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.pointer = (mw // 2, mh // 2)
        self._draw(*self.pointer)
        with ocr_lock:
            ocr_state.update(active=True, status="selecting", text="", error="")

    def _motion(self, event) -> None:
        self.pointer = (int(event.x), int(event.y))
        self._draw(*self.pointer)

    def _draw(self, x: int, y: int) -> None:
        half_w = self.rect_w // 2
        half_h = self.rect_h // 2
        x = max(half_w, min(self.monitor[2] - half_w, x))
        y = max(half_h, min(self.monitor[3] - half_h, y))
        self.canvas.delete("all")
        self.canvas.create_rectangle(
            x - half_w,
            y - half_h,
            x + half_w,
            y + half_h,
            outline="#3ecf8e",
            width=3,
        )
        self.canvas.create_text(
            x,
            y - half_h - 18,
            text=self._instruction,
            fill="#ffffff",
            font=("Segoe UI", 11, "bold"),
        )

    def _click(self, event) -> None:
        ml, mt, mw, mh = self.monitor
        half_w = self.rect_w // 2
        half_h = self.rect_h // 2
        cx = max(half_w, min(mw - half_w, int(event.x)))
        cy = max(half_h, min(mh - half_h, int(event.y)))
        bbox = (
            ml + cx - half_w,
            mt + cy - half_h,
            ml + cx + half_w,
            mt + cy + half_h,
        )
        self.win.withdraw()
        callback = self._selection_callback
        self._selection_callback = None
        if callback is not None:
            with ocr_lock:
                ocr_state.update(active=False, status="idle", text="", error="")
            callback(bbox, (ml + cx, mt + cy))
            return
        with ocr_lock:
            ocr_state.update(active=False, status="reading", text="", error="")
        self.root.after(120, lambda: threading.Thread(
            target=self._recognize,
            args=(bbox,),
            daemon=True,
        ).start())

    def read_fixed(self) -> None:
        self.win.withdraw()
        with ocr_lock:
            ocr_state.update(active=True, status="reading", text="", error="")
        threading.Thread(target=self._run_fixed_ocr, daemon=True).start()

    def _run_fixed_ocr(self) -> None:
        try:
            game_input = WindowsGameInput()
            if game_input.find_window():
                game_input.focus_game()
                time.sleep(0.1)
            bbox = game_coordinate_box()
            copied = self.recognize_bbox(bbox, save_debug=True)
            self.root.after(0, lambda value=copied: self._copy_result(value))
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            with ocr_lock:
                ocr_state.update(active=False, status="error", text="", error=message)
            print(f"OCR error: {message}", flush=True)

    def _recognize(self, bbox: Tuple[int, int, int, int]) -> None:
        try:
            copied = self.recognize_bbox(bbox, save_debug=True)
            self.root.after(0, lambda value=copied: self._copy_result(value))
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            with ocr_lock:
                ocr_state.update(active=False, status="error", text="", error=message)
            print(f"OCR error: {message}", flush=True)

    def recognize_bbox(
        self,
        bbox: Tuple[int, int, int, int],
        save_debug: bool = False,
        fast: bool = False,
    ) -> str:
        collector, ocr_reason = current_ocr_context()
        lock_t0 = time.perf_counter()
        self._recognition_lock.acquire()
        lock_wait_ms = (time.perf_counter() - lock_t0) * 1000.0
        try:
            if collector is not None and lock_wait_ms >= 0.05:
                collector.add_lock("_recognition_lock", lock_wait_ms)

            capture_ms = 0.0
            preproc_ms = 0.0
            inference_ms = 0.0
            variants_count = 0
            variant_scores: List[dict] = []
            winning_variant_idx = -1
            first_candidate = ""
            consensus_count = 0

            t_cap = time.perf_counter()
            image = grab_bbox_rgb(bbox)
            capture_ms = (time.perf_counter() - t_cap) * 1000.0
            try:
                import numpy as np
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:
                raise RuntimeError("OCR is not installed. Restart using start.bat.") from exc
            if not fast and self._ocr_engine is None:
                self._ocr_engine = RapidOCR()
            if self._ocr_direct_engine is None:
                self._ocr_direct_engine = RapidOCR(
                    use_text_det=False,
                    use_angle_cls=False,
                )
            copied = ""
            raw_attempts: List[str] = []
            votes: Dict[str, Tuple[int, float]] = {}

            t_pre = time.perf_counter()
            all_focused = prepare_focused_coordinate_images(image)
            if fast:
                focused_images = [
                    all_focused[i]
                    for i in OCR_FAST_CROP_ORDER
                    if 0 <= i < len(all_focused)
                ][:OCR_FAST_MAX_VARIANTS]
            else:
                focused_images = all_focused
            preproc_ms += (time.perf_counter() - t_pre) * 1000.0

            for focused in focused_images:
                t_inf = time.perf_counter()
                result, _elapsed = self._ocr_direct_engine(np.asarray(focused))
                inference_ms += (time.perf_counter() - t_inf) * 1000.0
                variants_count += 1
                parts = [str(item[1]).strip() for item in (result or []) if len(item) > 1]
                raw_text = " ".join(part for part in parts if part).strip()
                raw_attempts.append(raw_text)
                candidate = normalize_coordinate_text(raw_text)
                confidence = 0.0
                if result:
                    confidence = sum(float(item[2]) for item in result if len(item) > 2) / max(
                        1, len(result)
                    )
                variant_scores.append({
                    "idx": variants_count - 1,
                    "stage": "focused",
                    "raw": raw_text,
                    "candidate": candidate,
                    "confidence": round(confidence, 4),
                })
                if not candidate:
                    continue
                if not first_candidate:
                    first_candidate = candidate
                count, score = votes.get(candidate, (0, 0.0))
                votes[candidate] = (count + 1, score + confidence)
                avg_conf = (score + confidence) / max(1, count + 1)
                # Early exit inside the loop (was after all variants — wasted work).
                if not fast and count + 1 >= 2:
                    copied = candidate
                    consensus_count = count + 1
                    winning_variant_idx = variants_count - 1
                    break
                if fast and (
                    count + 1 >= 3
                    or (
                        count + 1 >= OCR_EARLY_EXIT_VOTES
                        and avg_conf >= max(OCR_EARLY_EXIT_MIN_CONF, 0.90)
                    )
                ):
                    copied = candidate
                    consensus_count = count + 1
                    winning_variant_idx = variants_count - 1
                    break

            if not copied and votes:
                candidate, (count, score_sum) = max(
                    votes.items(),
                    key=lambda item: (item[1][0], item[1][1]),
                )
                avg_conf = score_sum / max(1, count)
                if count >= 2 and not fast:
                    copied = candidate
                    consensus_count = count
                    for vs in variant_scores:
                        if vs.get("candidate") == candidate:
                            winning_variant_idx = int(vs["idx"])
                            break
                elif fast and (
                    count >= 3
                    or (count >= OCR_EARLY_EXIT_VOTES and avg_conf >= OCR_EARLY_EXIT_MIN_CONF)
                ):
                    copied = candidate
                    consensus_count = count
                    for vs in variant_scores:
                        if vs.get("candidate") == candidate:
                            winning_variant_idx = int(vs["idx"])
                            break

            if not copied:
                t_pre = time.perf_counter()
                prepared_images = prepare_white_text_images(image)
                preproc_ms += (time.perf_counter() - t_pre) * 1000.0
            debug_dir = PROJECT_ROOT / ".cache" / "ocr-debug"
            if save_debug:
                debug_dir.mkdir(parents=True, exist_ok=True)
                image.save(debug_dir / "last-capture.png")
            if not copied:
                fallback_images = (
                    [prepared_images[index] for index in (0, 3, 4)]
                    if fast
                    else prepared_images
                )
                for index, prepared in enumerate(fallback_images):
                    if save_debug:
                        prepared.save(debug_dir / f"last-mask-{index + 1}.png")
                    engines = [(self._ocr_direct_engine, {})]
                    if not fast:
                        engines.append((self._ocr_engine, {
                                "box_thresh": 0.2,
                                "text_score": 0.2,
                                "unclip_ratio": 1.8,
                            }))
                    for engine, kwargs in engines:
                        t_inf = time.perf_counter()
                        result, _elapsed = engine(np.asarray(prepared), **kwargs)
                        inference_ms += (time.perf_counter() - t_inf) * 1000.0
                        variants_count += 1
                        parts = [str(item[1]).strip() for item in (result or []) if len(item) > 1]
                        raw_text = " ".join(part for part in parts if part).strip()
                        raw_attempts.append(raw_text)
                        candidate = normalize_coordinate_text(raw_text)
                        confidence = 0.0
                        if result:
                            confidence = sum(
                                float(item[2]) for item in result if len(item) > 2
                            ) / max(1, len(result))
                        variant_scores.append({
                            "idx": variants_count - 1,
                            "stage": "white_mask",
                            "mask_index": index,
                            "raw": raw_text,
                            "candidate": candidate,
                            "confidence": round(confidence, 4),
                        })
                        if fast and candidate:
                            if not first_candidate:
                                first_candidate = candidate
                            count, score = votes.get(candidate, (0, 0.0))
                            votes[candidate] = (count + 1, score + confidence)
                        elif candidate:
                            copied = candidate
                            winning_variant_idx = variants_count - 1
                            consensus_count = 1
                            break
                    if copied:
                        break
            if fast and votes and not copied:
                candidate, (count, _score) = max(
                    votes.items(),
                    key=lambda item: (item[1][0], item[1][1]),
                )
                if count >= 2:
                    copied = candidate
                    consensus_count = count
                    for vs in variant_scores:
                        if vs.get("candidate") == candidate:
                            winning_variant_idx = int(vs["idx"])
                            break
            if collector is not None:
                collector.add_ocr_event(
                    reason=ocr_reason,
                    capture_ms=capture_ms,
                    preproc_ms=preproc_ms,
                    inference_ms=inference_ms,
                    variants_count=variants_count,
                    winning_variant_idx=winning_variant_idx,
                    result=copied or None,
                    consensus_count=consensus_count,
                    all_scores=[vs.get("confidence") for vs in variant_scores],
                    variant_scores=variant_scores,
                    first_variant_won=bool(
                        first_candidate and copied and first_candidate == copied
                    ),
                )
            if copied:
                win_confs = [
                    float(vs.get("confidence") or 0.0)
                    for vs in variant_scores
                    if vs.get("candidate") == copied
                ]
                avg_win = sum(win_confs) / max(1, len(win_confs)) if win_confs else 0.0
                if votes.get(copied):
                    count, score_sum = votes[copied]
                    avg_win = score_sum / max(1, count)
                record_ocr_meta(avg_win, consensus_count)
            if not copied:
                print(f"OCR white-mask raw: {raw_attempts}", flush=True)
                raise RuntimeError("No white coordinate text was recognized.")
            return copied
        finally:
            self._recognition_lock.release()

    def _copy_result(self, value: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()
        with ocr_lock:
            ocr_state.update(active=False, status="copied", text=value, error="")
        print(f"OCR copied: {value}", flush=True)

    def cancel(self) -> None:
        self.win.withdraw()
        callback = self._selection_callback
        self._selection_callback = None
        if callback is not None:
            update_game_marker_state(
                active=False,
                status="cancelled",
                message="Selection cancelled",
                error="Automation cancelled",
            )
        with ocr_lock:
            ocr_state.update(active=False, status="cancelled", text="", error="")


_mss_lock = threading.Lock()
_mss_camera = None


def grab_bbox_rgb(bbox: Tuple[int, int, int, int]) -> Image.Image:
    """Capture screen ROI as RGB. Prefer reused mss session; fall back to ImageGrab."""
    global _mss_camera
    left, top, right, bottom = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
    width = max(1, right - left)
    height = max(1, bottom - top)
    with _mss_lock:
        try:
            import mss

            if _mss_camera is None:
                _mss_camera = mss.mss()
            shot = _mss_camera.grab({"left": left, "top": top, "width": width, "height": height})
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception:
            _mss_camera = None
            return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).convert("RGB")


def normalize_coordinate_text(text: str) -> str:
    import re

    cleaned = (
        str(text or "")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("_", "-")
        .replace("O", "0")
        .replace("o", "0")
    )
    numbers = re.findall(r"-?\d{1,8}", cleaned)
    normalized: List[int] = []
    for token in numbers:
        negative = token.startswith("-")
        digits = token.lstrip("-")
        while len(digits) > 1 and int(digits) > 9999:
            digits = digits[:-1]
        value = int(digits)
        if value <= 9999:
            normalized.append(-value if negative else value)
    if len(normalized) >= 2:
        return f"{normalized[0]}, {normalized[1]}"
    return ""


def prepare_white_text_images(image: Image.Image) -> List[Image.Image]:
    """Keep only white or light gray text and remove colored backgrounds."""
    import numpy as np

    source = image.convert("RGB")
    width, height = source.size
    focus_w = min(width, 120)
    focus_h = min(height, 28)
    focused = source.crop((
        (width - focus_w) // 2,
        (height - focus_h) // 2,
        (width + focus_w) // 2,
        (height + focus_h) // 2,
    ))
    variants: List[Image.Image] = [
        focused.resize(
            (focused.width * 5, focused.height * 5),
            Image.Resampling.LANCZOS,
        )
    ]
    rgb = np.asarray(source)
    minimum = rgb.min(axis=2)
    spread = rgb.max(axis=2) - minimum
    for brightness, chroma in ((190, 40), (145, 75)):
        white = (minimum >= brightness) & (spread <= chroma)
        mask = np.where(white, 255, 0).astype(np.uint8)
        mask = crop_to_densest_white_line(mask)
        binary = Image.fromarray(mask, mode="L").filter(ImageFilter.MaxFilter(3))
        scaled = binary.resize(
            (binary.width * 4, binary.height * 4),
            Image.Resampling.NEAREST,
        )
        variants.extend((ImageOps.invert(scaled).convert("RGB"), scaled.convert("RGB")))
    return variants


def prepare_focused_coordinate_images(image: Image.Image) -> List[Image.Image]:
    """Generate shifted crops around the click for consensus voting."""
    source = image.convert("RGB")
    width, height = source.size
    crop_w = min(width, 120)
    crop_h = min(height, 28)
    images: List[Image.Image] = []
    for offset_y in (-8, 0, 8):
        for offset_x in (-24, -12, 0, 12, 24):
            center_x = max(crop_w // 2, min(width - crop_w // 2, width // 2 + offset_x))
            center_y = max(crop_h // 2, min(height - crop_h // 2, height // 2 + offset_y))
            crop = source.crop((
                center_x - crop_w // 2,
                center_y - crop_h // 2,
                center_x + crop_w // 2,
                center_y + crop_h // 2,
            ))
            images.append(crop.resize(
                (crop.width * 5, crop.height * 5),
                Image.Resampling.LANCZOS,
            ))
    return images


def crop_to_densest_white_line(mask):
    """Crop the horizontal strip most likely to contain coordinates."""
    import numpy as np

    active_rows = np.where((mask > 0).sum(axis=1) >= 2)[0]
    if active_rows.size == 0:
        return mask
    runs = np.split(active_rows, np.where(np.diff(active_rows) > 2)[0] + 1)
    run = max(runs, key=lambda rows: int((mask[rows] > 0).sum()))
    top = max(0, int(run[0]) - 4)
    bottom = min(mask.shape[0], int(run[-1]) + 5)
    band = mask[top:bottom]
    active_cols = np.where((band > 0).sum(axis=0) >= 1)[0]
    if active_cols.size == 0:
        return band
    left = max(0, int(active_cols[0]) - 6)
    right = min(mask.shape[1], int(active_cols[-1]) + 7)
    return band[:, left:right]


def largest_monitor() -> Tuple[int, int, int, int]:
    """Return the largest monitor as left, top, width, and height."""
    if not hasattr(ctypes, "windll") or MonitorEnumProc is None:
        return 0, 0, 1920, 1080

    rects: List[Tuple[int, int, int, int]] = []

    def _cb(_hmon, _hdc, lprc, _data):
        r = lprc.contents
        w = int(r.right - r.left)
        h = int(r.bottom - r.top)
        if w > 0 and h > 0:
            rects.append((int(r.left), int(r.top), w, h))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_cb), 0)
    if not rects:
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        return 0, 0, int(w), int(h)
    return max(rects, key=lambda m: m[2] * m[3])


def hud_anchor_xy() -> Tuple[int, int]:
    """
    Tooltip position below the Palworld map coordinate HUD.
    Validated at 2560x1440 at origin; scales by monitor percentage.
    """
    ml, mt, mw, mh = largest_monitor()
    x = ml + int(mw * 0.12)
    y = mt + int(mh * 0.178)
    return x, y


def _blank_tile_jpeg() -> bytes:
    path = TILE_DISK / "blank-256.jpg"
    if path.is_file() and path.stat().st_size > 32:
        return path.read_bytes()
    img = Image.new("RGB", (256, 256), (11, 18, 32))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=40)
    data = buf.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _http_get_bytes(url: str, referer: str, attempts: int = 2) -> bytes:
    last_exc: Exception | None = None
    headers = {
        "Referer": referer,
        "User-Agent": _TILE_FETCH_UA,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for i in range(attempts):
        try:
            with _TILE_FETCH_LOCK:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    return resp.read()
        except urllib.error.HTTPError as exc:
            # MapGenie returns 403 for tiles outside content
            if exc.code in (403, 404):
                return _blank_tile_jpeg()
            last_exc = exc
            time.sleep(0.2 * (i + 1))
        except Exception as exc:
            last_exc = exc
            time.sleep(0.2 * (i + 1))
    assert last_exc is not None
    raise last_exc


def _image_cache_get(cache: OrderedDict, key) -> Optional[bytes]:
    with _IMAGE_CACHE_LOCK:
        data = cache.get(key)
        if data is not None:
            cache.move_to_end(key)
        return data


def _image_cache_put(cache: OrderedDict, key, data: bytes, max_bytes: int) -> None:
    with _IMAGE_CACHE_LOCK:
        cache[key] = data
        cache.move_to_end(key)
        while cache and sum(map(len, cache.values())) > max_bytes:
            cache.popitem(last=False)


def fetch_map_icon_bytes(url: str) -> bytes:
    """Secure paldb icon proxy with CORS and disk caching."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc not in ICON_ALLOWED_HOSTS:
        raise ValueError("icon host not allowed")
    key = url
    cached = _image_cache_get(ICON_BYTES_CACHE, key)
    if cached is not None:
        return cached
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    ext = Path(parsed.path).suffix.lower() or ".webp"
    if ext not in (".webp", ".png", ".jpg", ".jpeg", ".svg", ".gif"):
        ext = ".webp"
    path = ICON_DISK / f"{digest}{ext}"
    for candidate in (BUNDLED_ICON_DISK / path.name, path):
        if candidate.is_file() and candidate.stat().st_size > 0:
            data = candidate.read_bytes()
            _image_cache_put(ICON_BYTES_CACHE, key, data, ICON_CACHE_MAX_BYTES)
            return data
    data = _http_get_bytes(url, "https://paldb.cc/en/Palpagos_Islands")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    _image_cache_put(ICON_BYTES_CACHE, key, data, ICON_CACHE_MAX_BYTES)
    return data


def fetch_tile_bytes(z: int, tx: int, ty: int) -> bytes:
    """Fetch a map tile from local cache (OFFLINE MODE)."""
    z = max(MAPGENIE_MIN_Z, min(MAPGENIE_MAX_Z, int(z)))
    n = 1 << z
    tx = max(0, min(n - 1, int(tx)))
    ty = max(0, min(n - 1, int(ty)))
    key = ("mg", z, tx, ty)
    cached = _image_cache_get(TILE_BYTES_CACHE, key)
    if cached is not None:
        return cached
    path = TILE_DISK / "mg" / f"z{z}" / f"{tx}_{ty}.jpg"
    if path.is_file() and path.stat().st_size > 64:
        data = path.read_bytes()
        _image_cache_put(TILE_BYTES_CACHE, key, data, TILE_CACHE_MAX_BYTES)
        return data
    # OFFLINE MODE: return blank tile instead of fetching from network
    print(f"[tile] missing: z{z}/{tx}_{ty} — run tools/download_map_tiles.py", flush=True)
    data = _blank_tile_jpeg()
    _image_cache_put(TILE_BYTES_CACHE, key, data, TILE_CACHE_MAX_BYTES)
    return data


def fetch_wt_tile_bytes(z: int, tx: int, ty: int) -> bytes:
    """Fetch a World Tree map tile from local cache (OFFLINE MODE)."""
    z = max(MAPGENIE_WT_MIN_Z, min(MAPGENIE_WT_MAX_Z, int(z)))
    n = 1 << z
    tx = max(0, min(n - 1, int(tx)))
    ty = max(0, min(n - 1, int(ty)))
    key = ("wt", z, tx, ty)
    cached = _image_cache_get(TILE_BYTES_CACHE, key)
    if cached is not None:
        return cached
    path = WT_TILE_DISK / f"z{z}" / f"{tx}_{ty}.jpg"
    if path.is_file() and path.stat().st_size > 64:
        data = path.read_bytes()
        _image_cache_put(TILE_BYTES_CACHE, key, data, TILE_CACHE_MAX_BYTES)
        return data
    # OFFLINE MODE: return blank tile instead of fetching from network
    print(f"[tile-wt] missing: z{z}/{tx}_{ty} — run tools/download_map_tiles.py", flush=True)
    data = _blank_tile_jpeg()
    _image_cache_put(TILE_BYTES_CACHE, key, data, TILE_CACHE_MAX_BYTES)
    return data


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[http]", fmt % args, flush=True)

    def _cors(self) -> None:
        # Ecoa só a origem local — nunca "*".
        origin = self.headers.get("Origin", "")
        if not _origin_is_local(origin):
            return
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _request_allowed(self) -> bool:
        """Recusa páginas de outros domínios (e DNS rebinding) antes de agir."""
        host = self.headers.get("Host")
        if host is not None and not _host_is_local(host):
            self._json(403, {"ok": False, "error": "forbidden host"})
            return False
        if not _origin_is_local(self.headers.get("Origin", "")):
            self._json(403, {"ok": False, "error": "forbidden origin"})
            return False
        return True

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _safe_static(self, path: str) -> Optional[Path]:
        rel = unquote(path.split("?", 1)[0])
        candidate = (DIST_ROOT / rel.lstrip("/")).resolve()
        if (
            str(candidate).startswith(str(DIST_ROOT))
            and candidate.is_file()
        ):
            return candidate
        index = DIST_ROOT / "index.html"
        if index.is_file() and "." not in Path(rel).name:
            return index
        return None

    def _file(self, path: Path) -> None:
        data = path.read_bytes()
        ctype, _ = mimetypes.guess_type(str(path))
        if path.suffix == ".webmanifest":
            ctype = "application/manifest+json"
        elif path.suffix == ".webp":
            ctype = "image/webp"
        if not ctype:
            ctype = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self._cors()
        if path.name in {"data.json", "index.html", "sw.js", "manifest.webmanifest"}:
            self.send_header("Cache-Control", "no-store")
        elif path.parent.name == "assets" and DIST_ROOT in path.parents:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        if not self._request_allowed():
            return
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not self._request_allowed():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/player-position/state":
            try:
                self._json(200, read_palworld_position())
            except OSError as exc:
                self._json(
                    500,
                    {
                        "ok": False,
                        "status": "probe_error",
                        "processFound": False,
                        "readAccess": False,
                        "pid": None,
                        "error": str(exc),
                    },
                )
            return

        if parsed.path == "/game-marker/state":
            t0 = time.perf_counter()
            with game_marker_lock:
                snap = dict(game_marker_state)
            collector = _current_timing_collector()
            if collector is None and MARKER_TIMING and game_marker_controller is not None:
                collector = getattr(game_marker_controller, "timing", None)
            if collector is not None and getattr(collector, "enabled", False):
                collector.add_http_poll((time.perf_counter() - t0) * 1000.0)
            self._json(200, {"ok": True, **snap})
            return

        if parsed.path == "/mouse-loop/state":
            with mouse_loop_lock:
                snap = dict(mouse_loop_state)
            active = bool(mouse_loop_controller and mouse_loop_controller.active)
            snap["active"] = active or bool(snap.get("active"))
            self._json(200, {"ok": True, **snap})
            return

        if parsed.path == "/autoloop/status":
            if autoloop_controller is None:
                self._json(503, {"ok": False, "error": "Auto Loop indisponível"})
                return
            self._json(200, {"ok": True, **autoloop_controller.snapshot()})
            return

        if parsed.path.startswith("/health") or parsed.path.startswith("/state"):
            with state_lock:
                snap = dict(state)
            px, py = hud_anchor_xy()
            self._json(200, {"ok": True, "version": VERSION, "anchor": [px, py], **snap})
            return

        if parsed.path.startswith("/ocr-state"):
            with ocr_lock:
                snap = dict(ocr_state)
            self._json(200, {"ok": True, **snap})
            return

        if parsed.path.startswith("/progress"):
            self._json(200, load_progress_file())
            return

        if parsed.path == "/map-tile":
            qs = parse_qs(parsed.query)
            try:
                z = int(float(qs.get("z", ["0"])[0]))
                tx = int(float(qs.get("x", ["0"])[0]))
                ty = int(float(qs.get("y", ["0"])[0]))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "params"})
                return
            use_wt = qs.get("map", [""])[0] == "wt"
            try:
                data = fetch_wt_tile_bytes(z, tx, ty) if use_wt else fetch_tile_bytes(z, tx, ty)
            except Exception as exc:
                print(f"map-tile error: {exc}", flush=True)
                self._json(502, {"ok": False, "error": str(exc)})
                return
            ctype = "image/jpeg"
            if data[:4] == b"RIFF":
                ctype = "image/webp"
            elif data[:3] == b"\xff\xd8\xff":
                ctype = "image/jpeg"
            elif data[:8] == b"\x89PNG\r\n\x1a\n":
                ctype = "image/png"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self._cors()
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path.startswith("/map-icon"):
            qs = parse_qs(parsed.query)
            src = (qs.get("src", [""])[0] or "").strip()
            if not src:
                self._json(400, {"ok": False, "error": "src"})
                return
            try:
                data = fetch_map_icon_bytes(src)
            except Exception as exc:
                print(f"map-icon error: {exc}", flush=True)
                self._json(502, {"ok": False, "error": str(exc)})
                return
            ctype = "image/webp"
            if data[:4] == b"<svg" or data[:5] == b"<?xml" or data.lstrip()[:4].lower() == b"<svg":
                ctype = "image/svg+xml"
            elif data[:8] == b"\x89PNG\r\n\x1a\n":
                ctype = "image/png"
            elif data[:3] == b"\xff\xd8\xff":
                ctype = "image/jpeg"
            elif data[:4] == b"RIFF":
                ctype = "image/webp"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self._cors()
            self.send_header("Cache-Control", "public, max-age=604800")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        static = self._safe_static(parsed.path)
        if static is not None:
            self._file(static)
            return

        self._json(404, {"ok": False})

    def do_POST(self):
        if not self._request_allowed():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"ok": False, "error": "content-length"})
            return
        if length < 0 or length > MAX_POST_BYTES:
            # `rfile.read(-1)` bloqueia a thread até o peer fechar — com um
            # ThreadingHTTPServer isso esgota as threads com requisições triviais.
            self._json(413, {"ok": False, "error": "payload too large"})
            return
        try:
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            body = json.loads(raw) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"ok": False})
            return

        if self.path.startswith("/game-marker/start"):
            if ocr_selector is None or game_marker_controller is None:
                self._json(503, {"ok": False, "error": "Game marker automation is unavailable"})
                return
            try:
                x = int(body["x"])
                y = int(body["y"])
            except (KeyError, TypeError, ValueError):
                self._json(400, {"ok": False, "error": "Valid target coordinates are required"})
                return
            with game_marker_lock:
                busy = bool(game_marker_state["active"])
            with ocr_lock:
                ocr_busy = ocr_state["status"] in ("selecting", "reading")
            if busy or ocr_busy or game_marker_controller.active or (
                autoloop_controller is not None and autoloop_controller.busy
            ):
                self._json(409, {"ok": False, "error": "OCR or game marker automation is active"})
                return
            confirm = not bool(body.get("dryRun", False))
            calibration_only = bool(body.get("calibrationOnly", False))
            update_game_marker_state(
                active=True,
                status="calibrating",
                target=[x, y],
                current=None,
                distanceMeters=None,
                calibration=None,
                message="Focusing Palworld and reading fixed coordinates",
                error="",
            )
            overlay.root.after(
                0,
                lambda: begin_game_marker_after_selection(
                    (x, y),
                    confirm,
                    calibration_only,
                    game_coordinate_box(),
                    game_screen_center(),
                ),
            )
            self._json(200, {"ok": True, "status": "calibrating"})
            return

        if self.path.startswith("/game-marker/cancel"):
            if game_marker_controller is not None:
                game_marker_controller.cancel()
            with game_marker_lock:
                selecting = game_marker_state["status"] == "selecting"
            if selecting and ocr_selector is not None:
                overlay.root.after(0, ocr_selector.cancel)
            else:
                update_game_marker_state(
                    active=False,
                    status="cancelled",
                    message="Automation cancelled",
                    error="",
                )
            self._json(200, {"ok": True, "status": "cancelled"})
            return

        if self.path.startswith("/autoloop/start"):
            if autoloop_controller is None:
                self._json(503, {"ok": False, "error": "Auto Loop indisponível"})
                return
            try:
                waits = {
                    k: max(0.0, min(3600.0, float(body.get(k, DEFAULT_WAITS[k]))))
                    for k in WAIT_KEYS
                }
                delay = max(0.0, min(5.0, float(body.get("inputDelay", DEFAULT_INPUT_DELAY))))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "Valores de espera inválidos"})
                return
            with game_marker_lock:
                gm_busy = bool(game_marker_state["active"])
            with ocr_lock:
                ocr_busy = ocr_state["status"] in ("selecting", "reading")
            if gm_busy or ocr_busy or (mouse_loop_controller and mouse_loop_controller.active):
                self._json(409, {"ok": False, "error": "Outra automação já está ativa"})
                return
            try:
                autoloop_controller.start(waits, delay)
            except AutoLoopError as exc:
                busy = "já está ativo" in str(exc)
                self._json(409 if busy else 400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "status": "running"})
            return

        if self.path.startswith("/autoloop/stop"):
            if autoloop_controller is not None:
                autoloop_controller.stop()
            self._json(200, {"ok": True, "status": "stopping"})
            return

        if self.path.startswith("/autoloop/reset"):
            if autoloop_controller is None:
                self._json(503, {"ok": False, "error": "Auto Loop indisponível"})
                return
            try:
                autoloop_controller.reset_positions()
            except AutoLoopError as exc:
                self._json(409, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "status": "reset"})
            return

        if self.path.startswith("/autoloop/calibrate"):
            if autoloop_controller is None:
                self._json(503, {"ok": False, "error": "Auto Loop indisponível"})
                return
            try:
                autoloop_controller.calibrate(str(body.get("target", "")))
            except AutoLoopError as exc:
                busy = "já está ativo" in str(exc)
                self._json(409 if busy else 400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "status": "calibrating"})
            return

        if self.path.startswith("/mouse-loop/start"):
            if mouse_loop_controller is None:
                self._json(503, {"ok": False, "error": "Mouse loop unavailable"})
                return
            try:
                interval = float(body.get("intervalSeconds", 40))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "Invalid interval"})
                return
            interval = max(1.0, min(3600.0, interval))
            with game_marker_lock:
                gm_busy = bool(game_marker_state["active"])
            with ocr_lock:
                ocr_busy = ocr_state["status"] in ("selecting", "reading")
            if gm_busy or ocr_busy or mouse_loop_controller.active or (
                autoloop_controller is not None and autoloop_controller.busy
            ):
                self._json(409, {"ok": False, "error": "Another automation is already active"})
                return
            update_mouse_loop_state(
                active=True,
                status="running",
                intervalSeconds=interval,
                message=f"Starting mouse combo loop every {interval:g}s",
                error="",
            )
            if not mouse_loop_controller.start(interval):
                update_mouse_loop_state(
                    active=False,
                    status="error",
                    message="Could not start mouse combo loop",
                    error="Could not start mouse combo loop",
                )
                self._json(409, {"ok": False, "error": "Mouse combo loop is already active"})
                return
            self._json(200, {"ok": True, "status": "running", "intervalSeconds": interval})
            return

        if self.path.startswith("/mouse-loop/stop"):
            if mouse_loop_controller is not None:
                mouse_loop_controller.cancel()
            update_mouse_loop_state(
                active=False,
                status="cancelled",
                message="Mouse combo loop stopped",
                error="",
            )
            self._json(200, {"ok": True, "status": "cancelled"})
            return

        if self.path.startswith("/set"):
            x = int(body.get("x", 0))
            y = int(body.get("y", 0))
            label = str(body.get("label") or "")
            with state_lock:
                state.update(active=True, x=x, y=y, label=label)
            if overlay:
                overlay.root.after(0, lambda: overlay.show(x, y, label))
            print(f"Tooltip ON ({x}, {y}) {label}", flush=True)
            self._json(200, {"ok": True})
            return

        if self.path.startswith("/clear"):
            with state_lock:
                state.update(active=False, x=0, y=0, label="")
            if overlay:
                overlay.root.after(0, overlay.hide)
            print("Tooltip OFF", flush=True)
            self._json(200, {"ok": True})
            return

        if self.path.startswith("/ocr-select"):
            if ocr_selector is None:
                self._json(503, {"ok": False, "error": "OCR unavailable"})
                return
            with ocr_lock:
                busy = ocr_state["status"] in ("selecting", "reading")
            with game_marker_lock:
                gm_busy = bool(game_marker_state["active"])
            if busy or gm_busy or (game_marker_controller and game_marker_controller.active):
                self._json(409, {"ok": False, "error": "OCR or game marker automation is active"})
                return
            overlay.root.after(0, ocr_selector.read_fixed)
            self._json(200, {"ok": True, "status": "reading"})
            return

        if self.path.startswith("/progress"):
            try:
                result = save_progress_file(body if isinstance(body, dict) else {})
            except Exception as exc:
                self._json(500, {"ok": False, "error": str(exc)})
                return
            if result.get("invalid"):
                self._json(400, {"ok": False, "error": "baseRevision is required"})
                return
            if result.get("conflict"):
                self._json(409, {"ok": False, "error": "revision conflict", **result})
                return
            self._json(200, result)
            return

        self._json(404, {"ok": False})


def start_server() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    server.serve_forever()


def _warmup_ocr() -> None:
    """Pre-load the ONNX model so the first real mark doesn't pay the cold-start cost.

    Acquires _recognition_lock so the warmup and the first real OCR call cannot
    race to initialise _ocr_direct_engine at the same time.
    """
    if ocr_selector is None:
        return
    try:
        import numpy as np
        # A fake crop at the typical 5x upscaled size (120x28 x 5 = 600x140)
        fake = np.zeros((140, 600, 3), dtype=np.uint8)
        with ocr_selector._recognition_lock:
            if ocr_selector._ocr_direct_engine is None:
                from rapidocr_onnxruntime import RapidOCR
                ocr_selector._ocr_direct_engine = RapidOCR(
                    use_text_det=False,
                    use_angle_cls=False,
                )
            ocr_selector._ocr_direct_engine(fake)
        print("[warmup] OCR engine pre-loaded", flush=True)
    except Exception as exc:
        print(f"[warmup] OCR warm-up skipped: {exc}", flush=True)


def main() -> None:
    global overlay, ocr_selector, game_marker_controller, mouse_loop_controller, autoloop_controller
    try:
        autoloop_controller = AutoLoop()
    except Exception as exc:
        print(f"Auto Loop init skipped: {exc}", flush=True)
    try:
        overlay = HudTooltip()
        ocr_selector = OcrSelector(overlay.root)
        game_marker_controller = GameMarkerController(
            read_game_coordinate,
            update_game_marker_state,
            position_hint=player_ingame_coordinate,
        )
        mouse_loop_controller = MouseComboLoop(update_mouse_loop_state)
        threading.Thread(target=_warmup_ocr, daemon=True).start()
    except Exception as exc:
        print(f"GUI/Automation init skipped: {exc}", flush=True)

    ml, mt, mw, mh = largest_monitor()
    ax, ay = hud_anchor_xy()
    print("=" * 50, flush=True)
    print(f"  COORD TOOLTIP {VERSION}", flush=True)
    print(f"  Monitor {mw}x{mh} @ ({ml},{mt})", flush=True)
    print(f"  Fixed HUD tooltip @ ({ax}, {ay})", flush=True)
    print(f"  http://127.0.0.1:{PORT}/", flush=True)
    print("=" * 50, flush=True)

    if overlay:
        threading.Thread(target=start_server, daemon=True).start()
        try:
            overlay.run()
        except KeyboardInterrupt:
            print("\nInterrupted.", flush=True)
        print("Exiting.", flush=True)
        os._exit(0)
    else:
        start_server()


if __name__ == "__main__":
    main()
