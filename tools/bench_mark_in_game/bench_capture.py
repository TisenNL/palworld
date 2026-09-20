#!/usr/bin/env python3
"""Compare ImageGrab vs mss vs dxcam on the coordinate ROI (200 samples)."""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache" / "timing"
sys.path.insert(0, str(ROOT))

N = 200


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def summarize(times: list[float]) -> dict:
    return {
        "n": len(times),
        "median_ms": round(statistics.median(times), 3) if times else None,
        "p95_ms": round(percentile(times, 95), 3) if times else None,
        "mean_ms": round(statistics.fmean(times), 3) if times else None,
        "min_ms": round(min(times), 3) if times else None,
        "max_ms": round(max(times), 3) if times else None,
    }


def roi_box() -> tuple[int, int, int, int]:
    try:
        from server.coord_tooltip import game_coordinate_box

        return game_coordinate_box()
    except Exception:
        from server.game_marker_automation import largest_monitor_bounds

        left, top, width, height = largest_monitor_bounds()
        cx = left + round(width * 0.142)
        cy = top + round(height * 0.153)
        bw = max(160, round(width * 0.07))
        bh = max(40, round(height * 0.03))
        return cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    box = roi_box()
    left, top, right, bottom = box
    w, h = right - left, bottom - top
    result: dict = {"roi": {"left": left, "top": top, "right": right, "bottom": bottom, "w": w, "h": h}}

    from PIL import ImageGrab

    times = []
    for _ in range(N):
        t0 = time.perf_counter()
        ImageGrab.grab(bbox=box, all_screens=True)
        times.append((time.perf_counter() - t0) * 1000.0)
    result["ImageGrab"] = summarize(times)

    try:
        import mss

        times = []
        with mss.mss() as sct:
            mon = {"left": left, "top": top, "width": w, "height": h}
            for _ in range(N):
                t0 = time.perf_counter()
                sct.grab(mon)
                times.append((time.perf_counter() - t0) * 1000.0)
        result["mss"] = summarize(times)
    except Exception as exc:
        result["mss"] = {"error": str(exc), "hint": "use .cache/bench-venv with mss installed"}

    try:
        import dxcam

        times = []
        cam = dxcam.create(output_idx=0, output_color="RGB")
        region = (left, top, right, bottom)
        for _ in range(N):
            t0 = time.perf_counter()
            frame = cam.grab(region=region)
            times.append((time.perf_counter() - t0) * 1000.0)
            if frame is None:
                pass
        result["dxcam"] = summarize(times)
        del cam
    except Exception as exc:
        result["dxcam"] = {"error": str(exc), "hint": "use .cache/bench-venv with dxcam installed"}

    path = OUT / "capture_bench.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
