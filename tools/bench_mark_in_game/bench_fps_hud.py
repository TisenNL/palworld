#!/usr/bin/env python3
"""Estimate HUD update rate via pixel-hash changes over ~3s."""
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
    from server.coord_tooltip import game_coordinate_box
    from server.game_marker_automation import WindowsGameInput

    gi = WindowsGameInput()
    if not gi.focus_game():
        print("ERRO: foque o Palworld.")
        sys.exit(2)
    box = game_coordinate_box()
    duration = 3.0
    t0 = time.perf_counter()
    samples = 0
    changes = 0
    last = None
    while time.perf_counter() - t0 < duration:
        img = ImageGrab.grab(bbox=box, all_screens=True)
        h = hash(img.tobytes())
        samples += 1
        if last is not None and h != last:
            changes += 1
        last = h
    elapsed = time.perf_counter() - t0
    payload = {
        "elapsed_s": round(elapsed, 3),
        "samples": samples,
        "sample_hz": round(samples / elapsed, 2),
        "hash_changes": changes,
        "change_hz": round(changes / elapsed, 2),
        "notes": [
            "FPS do jogo não é lido pela API; use contador do jogo ou NVIDIA overlay.",
            "change_hz aproxima a taxa em que o HUD (ou anti-aliasing) muda na ROI.",
            "Com mapa parado, change_hz deve ser baixo; mova o mapa para medir refresh do texto.",
        ],
    }
    path = OUT / "fps_hud.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
