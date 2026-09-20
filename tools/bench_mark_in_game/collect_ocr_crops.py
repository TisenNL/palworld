#!/usr/bin/env python3
"""Collect 300+ labeled HUD ROI crops into .cache/ocr-bench/."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache" / "ocr-bench"
sys.path.insert(0, str(ROOT))

TARGET = 300


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    from PIL import ImageGrab
    from server.coord_tooltip import game_coordinate_box, read_game_coordinate
    from server.game_marker_automation import WindowsGameInput

    gi = WindowsGameInput()
    if not gi.focus_game():
        print("ERRO: foque o Palworld com o mapa aberto.")
        sys.exit(2)

    box = game_coordinate_box()
    left, top, right, bottom = box
    w, h = right - left, bottom - top
    labels_path = OUT / "labels.jsonl"
    meta = {
        "roi": {"left": left, "top": top, "right": right, "bottom": bottom, "w": w, "h": h},
        "text_color_note": "HUD tipicamente texto claro/branco sobre fundo escuro/semitransparente; varia com UI do mapa",
        "target": TARGET,
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Coletando {TARGET} recortes da ROI {w}x{h}. Mova o mapa lentamente para variar o valor.")
    print("Ctrl+C para parar cedo.")
    count = 0
    last = None
    stable = 0
    with labels_path.open("a", encoding="utf-8") as fh:
        while count < TARGET:
            coord = read_game_coordinate(box)
            if coord is None:
                time.sleep(0.05)
                continue
            if coord == last:
                stable += 1
            else:
                stable = 0
                last = coord
            if stable < 2:
                time.sleep(0.04)
                continue
            img = ImageGrab.grab(bbox=box, all_screens=True)
            name = f"{count:04d}_{coord[0]}_{coord[1]}.png"
            img.save(OUT / name)
            fh.write(json.dumps({"file": name, "x": coord[0], "y": coord[1]}) + "\n")
            fh.flush()
            count += 1
            if count % 25 == 0:
                print(f"  {count}/{TARGET}")
            # nudge variety: small W tap every 10 samples
            if count % 10 == 0:
                gi.tap_key("D" if count % 20 == 0 else "A", 0.04)
                time.sleep(0.25)
                last = None
                stable = 0
            else:
                time.sleep(0.08)
    print(f"OK: {count} arquivos em {OUT}")


if __name__ == "__main__":
    main()
