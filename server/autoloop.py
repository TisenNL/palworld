from __future__ import annotations

import ctypes
import difflib
import json
import re
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Optional

from PIL import Image

from .game_marker_automation import LEFT_DOWN, LEFT_UP, WindowsGameInput

# Os botões são localizados por OCR na janela do jogo (nada a calibrar). Cada alvo
# aceita textos alternativos (ex.: outro idioma do jogo); edite aqui se necessário.
OCR_TARGETS: dict[str, tuple[str, ...]] = {
    "RETURN_TO_TITLE": ("Return to Title",),
    "YES": ("Yes",),
    "START_GAME": ("Start Game",),
    "PALPAGOS_ISLANDS": ("Palpagos Islands",),
    "START_GAME_2": ("Start Game",),
}
OCR_FIND_TIMEOUT = 20.0
OCR_RETRY_PAUSE = 0.4
OCR_MAX_WIDTH = 1600
OCR_MIN_SCORE = 0.5
OCR_FUZZY_RATIO = 0.8

# Fallback manual opcional: posições relativas ao canto da janela do Palworld, usadas
# só se o OCR não achar o texto. None = sem fallback.
AUTOLOOP_COORDS: dict[str, Optional[tuple[int, int]]] = {
    "RETURN_TO_TITLE": None,
    "YES": None,
    "START_GAME": None,
    "PALPAGOS_ISLANDS": None,
    "START_GAME_2": None,
}

DEFAULT_INPUT_DELAY = 0.15
CALIBRATION_COUNTDOWN = 3.0
POLL_SLICE = 0.05
VK_F10 = 0x79
CLICK_HOLD = 0.12
# Posições aprendidas (OCR na 1ª vez, ou calibração manual) + tamanho da janela em que valem.
COORDS_CACHE_PATH = Path(__file__).resolve().parent.parent / ".cache" / "autoloop-positions.json"

STEPS = (
    "Tecla E (lançar Pal)",
    "Espera após lançar",
    "Clique esquerdo (ataque)",
    "Espera 1",
    "Esc",
    "Return to Title",
    "Yes",
    "Espera após Yes",
    "Start Game",
    "Palpagos Islands",
    "Start Game",
    "Espera 2",
)
WAIT_STEPS = frozenset({1, 3, 7, 11})
WAIT_KEYS = ("afterThrow", "wait1", "afterYes", "wait2")
DEFAULT_WAITS = {"afterThrow": 2.0, "wait1": 0.0, "afterYes": 3.0, "wait2": 0.0}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def text_matches(found: str, wanted: str) -> bool:
    """Textos curtos (ex.: "Yes") exigem igualdade; os longos aceitam OCR levemente errado."""
    a, b = _norm(found), _norm(wanted)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(b) <= 4:
        return False
    return b in a or difflib.SequenceMatcher(None, a, b).ratio() >= OCR_FUZZY_RATIO


def pick_match(
    items: list[tuple[str, float, float, float]], wanted: tuple[str, ...]
) -> Optional[tuple[float, float]]:
    """items = (texto, score, cx, cy). Devolve o centro da melhor ocorrência."""
    best: Optional[tuple[float, float, float]] = None
    for text, score, cx, cy in items:
        if score < OCR_MIN_SCORE or not any(text_matches(text, w) for w in wanted):
            continue
        if best is None or score > best[0]:
            best = (score, cx, cy)
    return (best[1], best[2]) if best else None


_ocr_engine = None


def _ocr_items(image: Image.Image) -> list[tuple[str, float, float, float]]:
    global _ocr_engine
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise AutoLoopError("OCR não instalado. Reinicie usando start.bat.") from exc
    if _ocr_engine is None:
        _ocr_engine = RapidOCR()
    result, _elapsed = _ocr_engine(np.asarray(image))
    items: list[tuple[str, float, float, float]] = []
    for entry in result or []:
        box, text, score = entry[0], str(entry[1]), float(entry[2])
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        items.append((text, score, sum(xs) / len(xs), sum(ys) / len(ys)))
    return items


class AutoLoopStopped(Exception):
    pass


class AutoLoopError(Exception):
    pass


def _enter_per_monitor_dpi() -> None:
    """DPI per-monitor só nesta thread: o jogo pode estar em outro monitor, com outra escala.

    Não altera o processo inteiro, para não afetar o "Mark in game".
    """
    try:
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass


def _load_saved_coords() -> tuple[Optional[tuple[int, int]], dict[str, tuple[int, int]]]:
    try:
        raw = json.loads(COORDS_CACHE_PATH.read_text(encoding="utf-8"))
        size = (int(raw["size"][0]), int(raw["size"][1]))
        pos = {
            k: (int(v[0]), int(v[1]))
            for k, v in raw["pos"].items()
            if k in AUTOLOOP_COORDS and isinstance(v, (list, tuple)) and len(v) == 2
        }
        return size, pos
    except (OSError, ValueError, TypeError, IndexError, KeyError, AttributeError):
        return None, {}


class AutoLoop:
    """Loop infinito de input no Palworld, numa única thread, parável via Event/F10."""

    def __init__(self, game_input: Optional[WindowsGameInput] = None) -> None:
        self.game_input = game_input or WindowsGameInput()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._calibrating = False
        self._coords: dict[str, Optional[tuple[int, int]]] = dict(AUTOLOOP_COORDS)
        self._coords_size, saved = _load_saved_coords()
        self._coords.update(saved)
        self._waits = dict(DEFAULT_WAITS)
        self._input_delay = DEFAULT_INPUT_DELAY
        self._f10_prev = False
        self._state = {
            "status": "idle",
            "step": "",
            "stepIndex": -1,
            "iterations": 0,
            "message": "",
            "error": "",
        }

    @property
    def active(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def busy(self) -> bool:
        return self.active or self._calibrating

    def _set(self, **changes) -> None:
        with self._lock:
            self._state.update(changes)

    def snapshot(self) -> dict:
        with self._lock:
            snap = dict(self._state)
            coords = {k: (list(v) if v else None) for k, v in self._coords.items()}
        snap.update(
            active=self.active,
            calibrating=self._calibrating,
            coords=coords,
            missingCoords=[k for k, v in coords.items() if v is None],
            waits=dict(self._waits),
            inputDelay=self._input_delay,
            steps=list(STEPS),
        )
        return snap

    # ── controle ────────────────────────────────────────────────────────────
    def start(self, waits: dict[str, float], input_delay: float) -> None:
        """Levanta AutoLoopError se não puder iniciar."""
        with self._lock:
            if self.busy:
                raise AutoLoopError("Auto Loop já está ativo")
            if not self.game_input.user32:
                raise AutoLoopError("Automação de input indisponível neste sistema")
            if not self.game_input.find_window():
                raise AutoLoopError("Janela do Palworld não encontrada")
            self._waits = {k: max(0.0, float(waits.get(k, DEFAULT_WAITS[k]))) for k in WAIT_KEYS}
            self._input_delay = max(0.0, input_delay)
            self._stop.clear()
            self._state.update(
                status="running", step="", stepIndex=-1, iterations=0,
                message="Iniciando · F10 para parar", error="",
            )
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _save_positions(self) -> None:
        with self._lock:
            payload = {
                "size": list(self._coords_size) if self._coords_size else None,
                "pos": {k: list(v) for k, v in self._coords.items() if v is not None},
            }
        try:
            COORDS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            COORDS_CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass

    def reset_positions(self) -> None:
        """Esquece tudo; o OCR volta a procurar os botões na próxima execução."""
        if self.busy:
            raise AutoLoopError("Auto Loop ou calibração já está ativo")
        with self._lock:
            self._coords = dict(AUTOLOOP_COORDS)
            self._coords_size = None
            self._state.update(message="Posições esquecidas; o OCR vai localizar de novo", error="")
        try:
            COORDS_CACHE_PATH.unlink()
        except OSError:
            pass

    def calibrate(self, name: str) -> None:
        with self._lock:
            if name not in self._coords:
                raise AutoLoopError(f"Alvo de calibração inválido: {name}")
            if self.busy:
                raise AutoLoopError("Auto Loop ou calibração já está ativo")
            self._calibrating = True
            self._state.update(
                status="calibrating", error="",
                message=f"Calibrando {name}: posicione o mouse sobre o botão",
            )
        threading.Thread(target=self._calibrate_run, args=(name,), daemon=True).start()

    def _calibrate_run(self, name: str) -> None:
        _enter_per_monitor_dpi()
        try:
            deadline = time.monotonic() + CALIBRATION_COUNTDOWN
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._set(message=f"Calibrando {name}: capturando em {remaining:.0f}s…")
                time.sleep(min(0.25, remaining))
            left, top, right, bottom = self._window_rect()
            cx, cy = self.game_input.cursor()
            x, y = cx - left, cy - top
            self._use_window_size((right - left, bottom - top))
            with self._lock:
                self._coords[name] = (x, y)
            self._save_positions()
            self._set(status="idle", message=f"{name} calibrado em ({x}, {y}) na janela do jogo", error="")
        except Exception as exc:
            msg = str(exc) or exc.__class__.__name__
            self._set(status="error", error=msg, message=msg)
        finally:
            self._calibrating = False

    # ── execução ────────────────────────────────────────────────────────────
    def _f10_pressed(self) -> bool:
        down = bool(self.game_input.user32.GetAsyncKeyState(VK_F10) & 0x8000)
        edge = down and not self._f10_prev
        self._f10_prev = down
        return edge

    def _checkpoint(self) -> float:
        """Aborta se parado; pausa enquanto o jogo estiver sem foco. Retorna segundos pausados."""
        paused_for = 0.0
        paused_at: Optional[float] = None
        while True:
            if self._stop.is_set() or self._f10_pressed():
                self._stop.set()
                raise AutoLoopStopped()
            if self.game_input.game_is_foreground():
                if paused_at is not None:
                    paused_for = time.monotonic() - paused_at
                    self._set(status="running", error="", message="Retomado")
                return paused_for
            if paused_at is None:
                paused_at = time.monotonic()
                if self.game_input.find_window():
                    msg = "Palworld perdeu o foco — pausado. Volte à janela do jogo."
                else:
                    msg = "Janela do Palworld não encontrada — pausado."
                self._set(status="paused", message=msg, error=msg)
            self._stop.wait(POLL_SLICE)

    def _wait(self, seconds: float) -> None:
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            deadline += self._checkpoint()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self._stop.wait(min(POLL_SLICE, remaining))

    def _gap(self) -> None:
        self._wait(self._input_delay)

    def _window_rect(self) -> tuple[int, int, int, int]:
        hwnd = self.game_input.find_window()
        if not hwnd:
            raise AutoLoopError("Janela do Palworld não encontrada")
        rect = wintypes.RECT()
        if not self.game_input.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            raise AutoLoopError("Não foi possível ler a posição da janela do Palworld")
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)

    def _locate_text(self, name: str) -> Optional[tuple[int, int]]:
        """Captura a janela do jogo, roda OCR e devolve a posição de tela do texto."""
        from .coord_tooltip import grab_bbox_rgb

        left, top, right, bottom = self._window_rect()
        width, height = right - left, bottom - top
        if width < 50 or height < 50:
            return None
        image = grab_bbox_rgb((left, top, right, bottom))
        # Reduz a captura para o OCR ficar rápido; a captura pode ter outra escala que o rect.
        scale = min(1.0, OCR_MAX_WIDTH / image.width)
        if scale < 1.0:
            image = image.resize((int(image.width * scale), int(image.height * scale)))
        pos = pick_match(_ocr_items(image), OCR_TARGETS[name])
        if pos is None:
            return None
        return (
            left + round(pos[0] / image.width * width),
            top + round(pos[1] / image.height * height),
        )

    def _use_window_size(self, size: tuple[int, int]) -> None:
        """Posições só valem para o tamanho de janela em que foram aprendidas."""
        with self._lock:
            if self._coords_size != size:
                self._coords = dict(AUTOLOOP_COORDS)
                self._coords_size = size

    def _click_text(self, name: str) -> None:
        """Usa a posição já aprendida; senão acha o texto por OCR (1ª vez), guarda e clica."""
        label = OCR_TARGETS[name][0]
        left, top, right, bottom = self._window_rect()
        self._use_window_size((right - left, bottom - top))
        known = self._coords.get(name)
        if known is not None:
            self._checkpoint()
            self.game_input.move_cursor(left + known[0], top + known[1])
            self._wait(0.08)
            self._press_left(0.05)
            return
        deadline = time.monotonic() + OCR_FIND_TIMEOUT
        while True:
            deadline += self._checkpoint()
            point = self._locate_text(name)
            if point is not None:
                left, top, _r, _b = self._window_rect()
                with self._lock:
                    self._coords[name] = (point[0] - left, point[1] - top)
                self._save_positions()
                break
            if time.monotonic() >= deadline:
                raise AutoLoopError(f'Texto "{label}" não encontrado na tela do jogo')
            self._set(message=f'Procurando "{label}" na tela…')
            self._wait(OCR_RETRY_PAUSE)
        self._checkpoint()
        self.game_input.move_cursor(*point)
        self._wait(0.08)
        self._press_left(0.05)

    def _press_left(self, hold: float) -> None:
        """Segura o botão: o jogo ignora down/up instantâneos (sem frame entre eles)."""
        self.game_input.user32.mouse_event(LEFT_DOWN, 0, 0, 0, 0)
        try:
            self._stop.wait(hold)
        finally:
            self.game_input.user32.mouse_event(LEFT_UP, 0, 0, 0, 0)

    def _step(self, index: int) -> None:
        self._set(stepIndex=index, step=STEPS[index], message=f"Passo {index + 1}/{len(STEPS)}: {STEPS[index]}")

    def _run(self) -> None:
        _enter_per_monitor_dpi()
        try:
            if not self.game_input.focus_game():
                raise AutoLoopError("Janela do Palworld não encontrada ou sem foco")
            self._f10_prev = bool(self.game_input.user32.GetAsyncKeyState(VK_F10) & 0x8000)
            actions = (
                lambda: self.game_input.tap_key("E", 0.05),
                lambda: self._wait(self._waits["afterThrow"]),
                lambda: self._press_left(CLICK_HOLD),
                lambda: self._wait(self._waits["wait1"]),
                lambda: self.game_input.tap_key("ESCAPE", 0.05),
                lambda: self._click_text("RETURN_TO_TITLE"),
                lambda: self._click_text("YES"),
                lambda: self._wait(self._waits["afterYes"]),
                lambda: self._click_text("START_GAME"),
                lambda: self._click_text("PALPAGOS_ISLANDS"),
                lambda: self._click_text("START_GAME_2"),
                lambda: self._wait(self._waits["wait2"]),
            )
            while True:
                for index, action in enumerate(actions):
                    self._checkpoint()
                    self._step(index)
                    action()
                    if index not in WAIT_STEPS:
                        self._gap()
                with self._lock:
                    self._state["iterations"] += 1
        except AutoLoopStopped:
            self._set(status="stopped", step="", stepIndex=-1, message="Auto Loop parado", error="")
        except Exception as exc:
            msg = str(exc) or exc.__class__.__name__
            self._set(status="error", message=msg, error=msg)
        finally:
            self._stop.set()
