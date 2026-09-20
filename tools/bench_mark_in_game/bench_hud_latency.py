#!/usr/bin/env python3
"""HUD latency after WASD taps — requires Palworld focused with map open."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache" / "timing"
sys.path.insert(0, str(ROOT))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    from PIL import ImageGrab
    from server.coord_tooltip import game_coordinate_box, game_screen_center, normalize_coordinate_text
    from server.game_marker_automation import WindowsGameInput
    from rapidocr_onnxruntime import RapidOCR
    import numpy as np

    gi = WindowsGameInput()
    if not gi.focus_game():
        print("ERRO: não foi possível focar o Palworld. Abra o mapa e rode de novo.")
        sys.exit(2)
    box = game_coordinate_box()
    gi.move_cursor(*game_screen_center())
    time.sleep(0.3)
    engine = RapidOCR(use_text_det=False, use_angle_cls=False)

    def sample_text() -> str:
        img = ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")
        result, _ = engine(np.asarray(img))
        parts = [str(item[1]).strip() for item in (result or []) if len(item) > 1]
        return normalize_coordinate_text(" ".join(p for p in parts if p))

    def sample_hash() -> str:
        img = ImageGrab.grab(bbox=box, all_screens=True)
        return str(hash(img.tobytes()))

    series = {}
    for hold in (0.012, 0.06, 0.22):
        before = sample_text()
        gi.tap_key("W", hold)
        t0 = time.perf_counter()
        points = []
        last_text = before
        settled_at = None
        while (time.perf_counter() - t0) < 0.5:
            t = (time.perf_counter() - t0) * 1000.0
            text = sample_text()
            h = sample_hash()
            changed = text != before and text != ""
            if changed and settled_at is None and text == last_text:
                # first time we see a new stable value across consecutive samples is approximate
                settled_at = t
            points.append({"t_ms": round(t, 1), "text": text, "hash": h, "changed": changed})
            last_text = text
            # aim ~10ms; OCR itself may be slower
            elapsed = time.perf_counter() - t0
            target = (len(points)) * 0.01
            if target > elapsed:
                time.sleep(target - elapsed)
        series[str(hold)] = {
            "hold_s": hold,
            "before": before,
            "settled_at_ms": settled_at,
            "samples": points,
            "note": "intervalo real >= custo OCR; use hash-only mode se OCR for lento demais",
        }
        time.sleep(0.4)

    path = OUT / "hud_latency.json"
    path.write_text(json.dumps(series, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path}")
    for k, v in series.items():
        print(f"hold={k}s settled_at_ms={v['settled_at_ms']} samples={len(v['samples'])}")


if __name__ == "__main__":
    main()
