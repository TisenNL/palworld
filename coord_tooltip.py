"""
Fixed coordinate tooltip for the map HUD, integrated with the Vue application.
Usage: py -3 coord_tooltip.py or start.bat
"""
from __future__ import annotations

import ctypes
import hashlib
import io
import json
import mimetypes
import os
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image, ImageFilter, ImageGrab, ImageOps
from game_marker_automation import GameMarkerController

PORT = 8765
VERSION = "tooltip-v20-game-marker"
ROOT = Path(__file__).resolve().parent
DIST_ROOT = ROOT / "dist"
PROGRESS_PATH = ROOT / "progress.json"
PROGRESS_LOCK = threading.Lock()
DATA_NAMES = {
    "/data.json",
    "/breed.json",
    "/map_icons.json",
}

# MapGenie Palpagos 1.0, pyramid z8-z16
MAPGENIE_TILE_BASE = "https://tiles.mapgenie.io/games/palworld/1-0/default-v1"
MAPGENIE_MIN_Z = 8
MAPGENIE_MAX_Z = 16
TILE_DISK = ROOT / "assets" / "map-tiles"
ICON_DISK = ROOT / "assets" / "map-icons"
ICON_ALLOWED_HOSTS = {"cdn.paldb.cc"}
TILE_BYTES_CACHE: Dict[Tuple[str, int, int, int], bytes] = {}
ICON_BYTES_CACHE: Dict[str, bytes] = {}
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


def update_game_marker_state(**changes) -> None:
    with game_marker_lock:
        game_marker_state.update(changes)


def read_game_coordinate(bbox: Tuple[int, int, int, int]) -> Optional[Tuple[int, int]]:
    if ocr_selector is None:
        return None
    try:
        value = ocr_selector.recognize_bbox(bbox, save_debug=True, fast=True)
        first, second = value.split(",", 1)
        return int(first.strip()), int(second.strip())
    except (RuntimeError, TypeError, ValueError):
        return None


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
        if not PROGRESS_PATH.is_file():
            return {
                "version": 1,
                "revision": 0,
                "checks": {key: {} for key in CHECK_KEYS},
                "breedOwned": {},
                "prefs": {},
                "updatedAt": "",
            }
        try:
            data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
        prefs = data.get("prefs") if isinstance(data.get("prefs"), dict) else {}
        return {
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


def save_progress_file(body: dict) -> dict:
    checks_in = body.get("checks") if isinstance(body.get("checks"), dict) else {}
    prefs_in = body.get("prefs") if isinstance(body.get("prefs"), dict) else {}
    owned_in = body.get("breedOwned") if isinstance(body.get("breedOwned"), dict) else {}
    checks: dict = {}
    for key in CHECK_KEYS:
        raw = checks_in.get(key)
        if not isinstance(raw, dict):
            checks[key] = {}
            continue
        checks[key] = {str(k): True for k, v in raw.items() if v}
    breed_owned = {str(k): True for k, v in owned_in.items() if v}
    payload = {
        "version": max(1, int(body.get("version") or 1)),
        "revision": max(0, int(body.get("revision") or 0)),
        "updatedAt": body.get("updatedAt") or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": checks,
        "breedOwned": breed_owned,
        "prefs": prefs_in,
    }
    with PROGRESS_LOCK:
        tmp = PROGRESS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(PROGRESS_PATH)
    return {
        "ok": True,
        "updatedAt": payload["updatedAt"],
        "counts": {k: len(v) for k, v in checks.items()},
        "owned": len(breed_owned),
    }
MonitorEnumProc = ctypes.WINFUNCTYPE(
    ctypes.c_bool,
    ctypes.c_ulong,
    ctypes.c_ulong,
    ctypes.POINTER(wintypes.RECT),
    ctypes.c_longlong,
)


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
        self.root.mainloop()


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
        with self._recognition_lock:
            image = ImageGrab.grab(bbox=bbox, all_screens=True).convert("RGB")
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
            focused_images = [] if fast else prepare_focused_coordinate_images(image)
            for focused in focused_images:
                result, _elapsed = self._ocr_direct_engine(np.asarray(focused))
                parts = [str(item[1]).strip() for item in (result or []) if len(item) > 1]
                raw_text = " ".join(part for part in parts if part).strip()
                raw_attempts.append(raw_text)
                candidate = normalize_coordinate_text(raw_text)
                if not candidate:
                    continue
                confidence = sum(float(item[2]) for item in result or []) / max(1, len(result or []))
                count, score = votes.get(candidate, (0, 0.0))
                votes[candidate] = (count + 1, score + confidence)
            if votes:
                candidate, (count, _score) = max(
                    votes.items(),
                    key=lambda item: (item[1][0], item[1][1]),
                )
                if count >= 2 and not fast:
                    copied = candidate

            prepared_images = prepare_white_text_images(image)
            debug_dir = ROOT / "assets" / "ocr-debug"
            if save_debug:
                debug_dir.mkdir(parents=True, exist_ok=True)
                image.save(debug_dir / "last-capture.png")
            if not copied:
                fallback_images = (
                    [prepared_images[index] for index in (3, 4)]
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
                        result, _elapsed = engine(np.asarray(prepared), **kwargs)
                        parts = [str(item[1]).strip() for item in (result or []) if len(item) > 1]
                        raw_text = " ".join(part for part in parts if part).strip()
                        raw_attempts.append(raw_text)
                        candidate = normalize_coordinate_text(raw_text)
                        if fast and candidate:
                            confidence = sum(float(item[2]) for item in result or []) / max(
                                1, len(result or [])
                            )
                            count, score = votes.get(candidate, (0, 0.0))
                            votes[candidate] = (count + 1, score + confidence)
                        elif candidate:
                            copied = candidate
                            break
                    if copied:
                        break
            if fast and votes:
                candidate, (count, _score) = max(
                    votes.items(),
                    key=lambda item: (item[1][0], item[1][1]),
                )
                if count >= 2:
                    copied = candidate
            if not copied:
                print(f"OCR white-mask raw: {raw_attempts}", flush=True)
                raise RuntimeError("No white coordinate text was recognized.")
            return copied

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


def fetch_map_icon_bytes(url: str) -> bytes:
    """Secure paldb icon proxy with CORS and disk caching."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc not in ICON_ALLOWED_HOSTS:
        raise ValueError("icon host not allowed")
    key = url
    cached = ICON_BYTES_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    ext = Path(parsed.path).suffix.lower() or ".webp"
    if ext not in (".webp", ".png", ".jpg", ".jpeg", ".svg", ".gif"):
        ext = ".webp"
    path = ICON_DISK / f"{digest}{ext}"
    if path.is_file() and path.stat().st_size > 0:
        data = path.read_bytes()
        ICON_BYTES_CACHE[key] = data
        return data
    data = _http_get_bytes(url, "https://paldb.cc/en/Palpagos_Islands")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    ICON_BYTES_CACHE[key] = data
    return data


def fetch_tile_bytes(z: int, tx: int, ty: int) -> bytes:
    """Fetch a map tile from MapGenie 1.0."""
    z = max(MAPGENIE_MIN_Z, min(MAPGENIE_MAX_Z, int(z)))
    n = 1 << z
    tx = max(0, min(n - 1, int(tx)))
    ty = max(0, min(n - 1, int(ty)))
    key = ("mg", z, tx, ty)
    cached = TILE_BYTES_CACHE.get(key)
    if cached is not None:
        return cached
    path = TILE_DISK / "mg" / f"z{z}" / f"{tx}_{ty}.jpg"
    if path.is_file() and path.stat().st_size > 64:
        data = path.read_bytes()
        TILE_BYTES_CACHE[key] = data
        return data
    url = f"{MAPGENIE_TILE_BASE}/{z}/{tx}/{ty}.jpg"
    data = _http_get_bytes(url, "https://mapgenie.io/palworld/maps/palpagos-islands")
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(data) > 800:
        path.write_bytes(data)
    TILE_BYTES_CACHE[key] = data
    return data


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[http]", fmt % args, flush=True)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

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
        if rel in DATA_NAMES:
            candidate = (ROOT / rel.lstrip("/")).resolve()
            if candidate.parent == ROOT and candidate.is_file():
                return candidate
            return None
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
        if path.name == "data.json":
            self.send_header("Cache-Control", "no-store")
        elif path.parent.name == "assets" and DIST_ROOT in path.parents:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/game-marker/state":
            with game_marker_lock:
                snap = dict(game_marker_state)
            self._json(200, {"ok": True, **snap})
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

        if parsed.path.startswith("/map-tile"):
            qs = parse_qs(parsed.query)
            try:
                z = int(float(qs.get("z", ["0"])[0]))
                tx = int(float(qs.get("x", ["0"])[0]))
                ty = int(float(qs.get("y", ["0"])[0]))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "params"})
                return
            try:
                data = fetch_tile_bytes(z, tx, ty)
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
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
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
            if busy or ocr_busy or game_marker_controller.active:
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
            if busy:
                self._json(409, {"ok": False, "error": "OCR is already active"})
                return
            overlay.root.after(0, ocr_selector.activate)
            self._json(200, {"ok": True, "status": "selecting"})
            return

        if self.path.startswith("/progress"):
            try:
                result = save_progress_file(body if isinstance(body, dict) else {})
            except Exception as exc:
                self._json(500, {"ok": False, "error": str(exc)})
                return
            self._json(200, result)
            return

        self._json(404, {"ok": False})


def start_server() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    server.serve_forever()


def main() -> None:
    global overlay, ocr_selector, game_marker_controller
    overlay = HudTooltip()
    ocr_selector = OcrSelector(overlay.root)
    game_marker_controller = GameMarkerController(
        read_game_coordinate,
        update_game_marker_state,
    )
    threading.Thread(target=start_server, daemon=True).start()
    ml, mt, mw, mh = largest_monitor()
    ax, ay = hud_anchor_xy()
    print("=" * 50, flush=True)
    print(f"  COORD TOOLTIP {VERSION}", flush=True)
    print(f"  Monitor {mw}x{mh} @ ({ml},{mt})", flush=True)
    print(f"  Fixed HUD tooltip @ ({ax}, {ay})", flush=True)
    print(f"  http://127.0.0.1:{PORT}/", flush=True)
    print("  Esc clears HUD · browser Stop server ends this process", flush=True)
    print("=" * 50, flush=True)
    overlay.run()
    print("Exiting.", flush=True)
    os._exit(0)


if __name__ == "__main__":
    main()
