from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .autoloop import (
    VK_F10,
    AutoLoop,
    AutoLoopError,
    AutoLoopStopped,
    _enter_per_monitor_dpi,
)

RANKS = ("Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master")
# Frações (x, y) da janela, medidas em 1365x768, onde clicar em cada rank / Pal / Ready.
RANK_X = (0.156, 0.283, 0.409, 0.517, 0.626, 0.734)
RANK_Y = 0.57
PAL_X = 0.24
PAL_Y = (0.345, 0.440, 0.535, 0.629, 0.724)
READY_POS = (0.24, 0.893)
CHALLENGE_POS = (0.302, 0.50)
YES_POS = (0.432, 0.663)
BLACK_LEVEL = 30
BLACK_RATIO = 0.85

WAIT_KEYS = (
    "afterF", "afterChallenge", "afterRank", "afterYes",
    "afterPal", "afterReady", "afterBlack", "beforeF",
)
DEFAULT_WAITS = {
    "afterF": 1.5, "afterChallenge": 1.0, "afterRank": 1.0, "afterYes": 2.0,
    "afterPal": 0.4, "afterReady": 1.0, "afterBlack": 1.0, "beforeF": 1.0,
}
DEFAULT_OPTIONS = {"blackCycles": 2, "findTimeout": 20.0, "battleTimeout": 600.0}


def validate_config(body: dict) -> dict:
    try:
        waits = {k: max(0.0, min(600.0, float(body.get(k, DEFAULT_WAITS[k])))) for k in WAIT_KEYS}
        opts = {
            "blackCycles": max(0, min(5, int(body.get("blackCycles", DEFAULT_OPTIONS["blackCycles"])))),
            "findTimeout": max(1.0, min(300.0, float(body.get("findTimeout", DEFAULT_OPTIONS["findTimeout"])))),
            "battleTimeout": max(10.0, min(3600.0, float(body.get("battleTimeout", DEFAULT_OPTIONS["battleTimeout"])))),
        }
        ranks = [str(r) for r in body.get("ranks", ["Platinum"])]
        pals = [int(p) for p in body.get("pals", [1, 2, 3])]
    except (TypeError, ValueError) as exc:
        raise AutoLoopError("Valores inválidos") from exc
    ranks = [r for r in RANKS if r in ranks]
    pals = sorted(set(pals))
    if not ranks:
        raise AutoLoopError("Marque ao menos um rank")
    if len(pals) != 3 or any(p < 1 or p > 5 for p in pals):
        raise AutoLoopError("Marque exatamente 3 Pals (1 a 5)")
    return {**waits, **opts, "ranks": ranks, "pals": pals}


class ArenaLoop(AutoLoop):
    """Loop de lutas na Arena: F → Challenge → rank → Yes → 3 Pals → Ready → luta → volta."""

    def __init__(self, game_input=None) -> None:
        super().__init__(game_input)
        self._cfg: dict = {}
        self._steps: list[str] = []

    def snapshot(self) -> dict:
        with self._lock:
            snap = dict(self._state)
        snap.update(active=self.active, calibrating=False, steps=list(self._steps), config=dict(self._cfg))
        return snap

    def start(self, cfg: dict) -> None:  # type: ignore[override]
        with self._lock:
            if self.busy:
                raise AutoLoopError("Arena Loop já está ativo")
            if not self.game_input.user32:
                raise AutoLoopError("Automação de input indisponível neste sistema")
            if not self.game_input.find_window():
                raise AutoLoopError("Janela do Palworld não encontrada")
            self._cfg = cfg
            self._stop.clear()
            self._state.update(
                status="running", step="", stepIndex=-1, iterations=0,
                message="Iniciando · F10 para parar", error="",
            )
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    # ── visão ───────────────────────────────────────────────────────────────
    def _grab(self, region: tuple[float, float, float, float] = (0, 0, 1, 1)):
        from .coord_tooltip import grab_bbox_rgb

        left, top, right, bottom = self._window_rect()
        w, h = right - left, bottom - top
        box = (left + int(w * region[0]), top + int(h * region[1]),
               left + int(w * region[2]), top + int(h * region[3]))
        return grab_bbox_rgb(box), box

    def _wait_for(self, what: Callable[[], Optional[object]], label: str, timeout: float):
        deadline = time.monotonic() + timeout
        while True:
            deadline += self._checkpoint()
            found = what()
            if found:
                return found
            if time.monotonic() >= deadline:
                raise AutoLoopError(f'Tempo esgotado aguardando "{label}"')
            self._set(message=f'Aguardando "{label}"…')
            self._wait(0.25)

    def _is_black(self) -> bool:
        import numpy as np

        image, _box = self._grab()
        pixels = np.asarray(image.resize((64, 36)))
        return float((pixels.max(axis=2) < BLACK_LEVEL).mean()) >= BLACK_RATIO

    # ── ações ───────────────────────────────────────────────────────────────
    def _click_screen(self, x: int, y: int) -> None:
        self._checkpoint()
        self.game_input.move_cursor(x - 4, y - 4)
        self._wait(0.08)
        self.game_input.move_cursor(x, y)
        self._wait(0.15)
        self._press_left(0.1)

    def _click_frac(self, fx: float, fy: float) -> None:
        left, top, right, bottom = self._window_rect()
        self._click_screen(left + round((right - left) * fx), top + round((bottom - top) * fy))

    def _wait_battle(self) -> None:
        for n in range(self._cfg["blackCycles"]):
            self._wait_for(self._is_black, f"tela preta {n + 1}", self._cfg["battleTimeout"])
            self._wait_for(lambda: not self._is_black(), f"sair do preto {n + 1}", 60.0)

    def _build(self) -> list[tuple[str, Callable[[], None]]]:
        cfg = self._cfg
        n = self._state["iterations"]
        rank = cfg["ranks"][n % len(cfg["ranks"])]
        rank_i = RANKS.index(rank)

        def wait(key: str) -> Callable[[], None]:
            return lambda: self._wait(cfg[key])

        def pal(p: int) -> Callable[[], None]:
            def action() -> None:
                self._click_frac(PAL_X, PAL_Y[p - 1])
                self._wait(cfg["afterPal"])
            return action

        steps: list[tuple[str, Callable[[], None]]] = [
            ("Tecla F (Join the Arena)", lambda: self.game_input.tap_key("F", 0.05)),
            ("Espera após F", wait("afterF")),
            ("Challenge", lambda: self._click_frac(*CHALLENGE_POS)),
            ("Espera após Challenge", wait("afterChallenge")),
            (f"Rank {rank}", lambda: self._click_frac(RANK_X[rank_i], RANK_Y)),
            ("Espera após rank", wait("afterRank")),
            ("Yes", lambda: self._click_frac(*YES_POS)),
            ("Espera após Yes", wait("afterYes")),
        ]
        steps += [(f"Pal {p}", pal(p)) for p in cfg["pals"]]
        steps += [
            ("Ready", lambda: self._click_frac(*READY_POS)),
            ("Espera após Ready", wait("afterReady")),
            ("Aguardar luta (tela preta)", self._wait_battle),
            ("Espera pós-preto", wait("afterBlack")),
            ("Espera antes do F", wait("beforeF")),
        ]
        return steps

    def _run(self) -> None:
        _enter_per_monitor_dpi()
        try:
            if not self.game_input.focus_game():
                raise AutoLoopError("Janela do Palworld não encontrada ou sem foco")
            self._f10_prev = bool(self.game_input.user32.GetAsyncKeyState(VK_F10) & 0x8000)
            threading.Thread(target=self._preload_ocr, daemon=True).start()
            while True:
                steps = self._build()
                self._steps = [label for label, _ in steps]
                for index, (label, action) in enumerate(steps):
                    self._checkpoint()
                    self._set(stepIndex=index, step=label, message=f"Passo {index + 1}/{len(steps)}: {label}")
                    action()
                with self._lock:
                    self._state["iterations"] += 1
        except AutoLoopStopped:
            self._set(status="stopped", step="", stepIndex=-1, message="Arena Loop parado", error="")
        except Exception as exc:
            msg = str(exc) or exc.__class__.__name__
            self._set(status="error", message=msg, error=msg)
        finally:
            self._stop.set()
