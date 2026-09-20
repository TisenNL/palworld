"""Detailed Mark-in-game timing collector (PALWORLD_MARKER_TIMING=1).

Zero-cost no-ops when disabled. Writes JSONL under .cache/timing/.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from pathlib import Path
from typing import Optional

Coordinate = tuple[int, int]

_TIMING_THREAD_LOCAL = threading.local()
TIMING_DIR = Path(__file__).resolve().parent.parent / ".cache" / "timing"


def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no", "off")


MARKER_TIMING = _env_flag("PALWORLD_MARKER_TIMING", "0")

# Last successful OCR consensus (shared by OCR + marker controller).
_last_ocr_meta: dict[str, float] = {"confidence": 0.0, "consensus": 0.0}


def record_ocr_meta(confidence: float, consensus: int) -> None:
    _last_ocr_meta["confidence"] = float(confidence)
    _last_ocr_meta["consensus"] = float(consensus)


def last_ocr_confidence() -> float:
    return float(_last_ocr_meta.get("confidence") or 0.0)


def last_ocr_consensus() -> int:
    return int(_last_ocr_meta.get("consensus") or 0)


def _current_timing_collector() -> Optional["TimingCollector"]:
    return getattr(_TIMING_THREAD_LOCAL, "collector", None)


def current_ocr_context() -> tuple[Optional["TimingCollector"], str]:
    col = _current_timing_collector()
    reason = col.ocr_reason if col is not None else "unknown"
    return col, reason


class TimingCollector:
    def __init__(self, enabled: Optional[bool] = None) -> None:
        self.enabled = MARKER_TIMING if enabled is None else bool(enabled)
        self.run_id = time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
        self.phase_ms: dict[str, float] = {}
        self.sleep_ms: dict[str, float] = {}
        self.ocr_reads = 0
        self.loop_iterations = 0
        self.iterations_within_12 = 0
        self._phase_started: dict[str, float] = {}
        self._sleep_phase = "other"
        self._events: list[dict] = []
        self._ocr_first_call = True
        self.ocr_cold_first_ms: Optional[float] = None
        self._iteration_ctx: Optional[dict] = None
        self._run_target: Optional[Coordinate] = None
        self._run_initial: Optional[Coordinate] = None
        self._t0_wall: float = time.perf_counter()
        self.ocr_reason: str = "unknown"
        self._last_ocr_total_ms: float = 0.0

    def _append(self, event: dict) -> None:
        if not self.enabled:
            return
        event.setdefault("t_wall_ms", (time.perf_counter() - self._t0_wall) * 1000.0)
        self._events.append(event)

    def flush(self) -> None:
        if not self.enabled or not self._events:
            return
        try:
            TIMING_DIR.mkdir(parents=True, exist_ok=True)
            path = TIMING_DIR / f"run-{self.run_id}.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                for ev in self._events:
                    fh.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
            self._events.clear()
            print(f"[timing-collector] wrote {path.name}", flush=True)
        except OSError as exc:
            print(f"[timing-collector] write failed: {exc}", flush=True)

    def register_thread(self) -> None:
        if self.enabled:
            _TIMING_THREAD_LOCAL.collector = self

    def unregister_thread(self) -> None:
        try:
            del _TIMING_THREAD_LOCAL.collector
        except AttributeError:
            pass

    def run_start(self, target: Coordinate, initial: Optional[Coordinate] = None) -> None:
        if not self.enabled:
            return
        self._run_target = target
        self._run_initial = initial
        self._t0_wall = time.perf_counter()
        dist = None
        if initial is not None:
            dist = round(math.hypot(target[0] - initial[0], target[1] - initial[1]) * 4.59)
        self._append({
            "type": "run_start",
            "target": list(target),
            "initial": list(initial) if initial is not None else None,
            "initial_distance_m": dist,
            "pid": os.getpid(),
        })
        self.register_thread()

    def run_end(self, status: str, final_current: Optional[Coordinate] = None) -> None:
        if not self.enabled:
            return
        exact = False
        if final_current is not None and self._run_target is not None:
            exact = tuple(final_current) == tuple(self._run_target)
        total_ms = (time.perf_counter() - self._t0_wall) * 1000.0
        self._append({
            "type": "run_end",
            "status": status,
            "total_ms": round(total_ms, 3),
            "total_ocr_reads": self.ocr_reads,
            "total_iterations": self.loop_iterations,
            "iterations_within_12": self.iterations_within_12,
            "exact_match": exact,
            "ocr_cold_first_ms": round(self.ocr_cold_first_ms, 3) if self.ocr_cold_first_ms else None,
        })
        self.flush()
        self.unregister_thread()

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
        ended = time.perf_counter()
        ms = (ended - started) * 1000.0
        self.phase_ms[name] = self.phase_ms.get(name, 0.0) + ms
        self._sleep_phase = "other"
        self._append({"type": "phase", "name": name, "ms": round(ms, 3)})

    def add_sleep(self, seconds: float) -> None:
        if not self.enabled:
            return
        phase = self._sleep_phase
        ms = seconds * 1000.0
        self.sleep_ms[phase] = self.sleep_ms.get(phase, 0.0) + ms
        self._append({"type": "sleep", "phase": phase, "seconds": round(seconds, 6), "ms": round(ms, 3)})
        self.iteration_add_sleep(seconds)

    def set_ocr_reason(self, reason: str) -> None:
        if self.enabled:
            self.ocr_reason = reason

    def record_ocr(self) -> None:
        if self.enabled:
            self.ocr_reads += 1

    def add_ocr_event(
        self,
        reason: str,
        capture_ms: float,
        preproc_ms: float,
        inference_ms: float,
        variants_count: int,
        winning_variant_idx: int,
        result: Optional[str],
        consensus_count: int,
        all_scores: Optional[list] = None,
        variant_scores: Optional[list] = None,
        first_variant_won: bool = False,
    ) -> None:
        if not self.enabled:
            return
        total_ms = capture_ms + preproc_ms + inference_ms
        cold = self._ocr_first_call
        if cold:
            self.ocr_cold_first_ms = total_ms
        self._ocr_first_call = False
        self._last_ocr_total_ms = total_ms
        self._append({
            "type": "ocr",
            "reason": reason or self.ocr_reason,
            "capture_ms": round(capture_ms, 3),
            "preproc_ms": round(preproc_ms, 3),
            "inference_ms": round(inference_ms, 3),
            "total_ms": round(total_ms, 3),
            "variants_count": variants_count,
            "winning_variant_idx": winning_variant_idx,
            "result": result,
            "consensus_count": consensus_count,
            "all_scores": all_scores,
            "variant_scores": variant_scores,
            "first_variant_won": bool(first_variant_won),
            "cold_start": cold,
        })

    def record_iteration(self) -> None:
        if self.enabled:
            self.loop_iterations += 1

    def iteration_begin(self, idx: int, dx: float, dy: float) -> None:
        if not self.enabled:
            return
        norm = math.hypot(dx, dy)
        if norm <= 12:
            self.iterations_within_12 += 1
        self._iteration_ctx = {
            "i": idx,
            "dx": round(dx, 3),
            "dy": round(dy, 3),
            "norm": round(norm, 3),
            "_t_start": time.perf_counter(),
            "_sleep_ms": 0.0,
            "_ocr_ms": 0.0,
            "_ocr_count": 0,
        }

    def iteration_add_sleep(self, seconds: float) -> None:
        if not self.enabled or self._iteration_ctx is None:
            return
        self._iteration_ctx["_sleep_ms"] += seconds * 1000.0

    def iteration_add_ocr(self, total_ms: float) -> None:
        if not self.enabled or self._iteration_ctx is None:
            return
        self._iteration_ctx["_ocr_ms"] += total_ms
        self._iteration_ctx["_ocr_count"] += 1

    def iteration_end(
        self,
        action_keys: list[str],
        action_duration: float,
        delta_obs: tuple[float, float],
    ) -> None:
        if not self.enabled or self._iteration_ctx is None:
            return
        ctx = self._iteration_ctx
        total_ms = (time.perf_counter() - ctx["_t_start"]) * 1000.0
        hold = action_duration * 1000.0
        sleep_ms = ctx["_sleep_ms"]
        ocr_ms = ctx["_ocr_ms"]
        other_ms = max(0.0, total_ms - hold - sleep_ms - ocr_ms)
        self._append({
            "type": "iteration",
            "i": ctx["i"],
            "dx": ctx["dx"],
            "dy": ctx["dy"],
            "norm": ctx["norm"],
            "action_keys": action_keys,
            "action_duration_ms": round(hold, 3),
            "delta_obs_x": round(delta_obs[0], 3),
            "delta_obs_y": round(delta_obs[1], 3),
            "ocr_count": ctx["_ocr_count"],
            "iter_total_ms": round(total_ms, 3),
            "breakdown_ms": {
                "hold": round(hold, 3),
                "sleep": round(sleep_ms, 3),
                "ocr": round(ocr_ms, 3),
                "other": round(other_ms, 3),
            },
        })
        self._iteration_ctx = None

    def add_win32(self, op: str, **kwargs) -> None:
        if not self.enabled:
            return
        ev = {"type": "win32", "op": op}
        ev.update({k: v for k, v in kwargs.items() if v is not None})
        self._append(ev)

    def add_focus(self, ms: float, success: bool) -> None:
        if not self.enabled:
            return
        self._append({"type": "focus", "ms": round(ms, 3), "success": bool(success)})

    def add_lock(self, name: str, wait_ms: float) -> None:
        if not self.enabled:
            return
        self._append({"type": "lock", "name": name, "wait_ms": round(wait_ms, 3)})

    def add_http_poll(self, ms: float) -> None:
        if not self.enabled:
            return
        self._append({"type": "http_poll", "ms": round(ms, 3)})

    def add_calibration(self, mode: str, reused_disk: bool = False, reused_memory: bool = False) -> None:
        if not self.enabled:
            return
        self._append({
            "type": "calibration",
            "mode": mode,
            "reused_disk": bool(reused_disk),
            "reused_memory": bool(reused_memory),
        })

    def log(self, prefix: str = "marker-timing") -> None:
        if not self.enabled:
            return
        total = sum(self.phase_ms.values())
        print(
            f"[{prefix}] phases_ms={{{', '.join(f'{k}={v:.1f}' for k, v in sorted(self.phase_ms.items()))}}}"
            f" sleep_ms={{{', '.join(f'{k}={v:.1f}' for k, v in sorted(self.sleep_ms.items()))}}}"
            f" ocr_reads={self.ocr_reads} loop_iters={self.loop_iterations} total_phase_ms={total:.1f}"
            f" jsonl=.cache/timing/run-{self.run_id}.jsonl",
            flush=True,
        )


RunTiming = TimingCollector
