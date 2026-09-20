#!/usr/bin/env python3
"""WASD physics: units/sec and variance — requires Palworld map focused."""
from __future__ import annotations

import json
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache" / "timing"
sys.path.insert(0, str(ROOT))


def parse_coord(text: str):
    a, b = text.split(",", 1)
    return int(a.strip()), int(b.strip())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    from server.coord_tooltip import game_coordinate_box, game_screen_center, read_game_coordinate
    from server.game_marker_automation import WindowsGameInput

    gi = WindowsGameInput()
    if not gi.focus_game():
        print("ERRO: foque o Palworld com o mapa aberto.")
        sys.exit(2)
    box = game_coordinate_box()
    gi.move_cursor(*game_screen_center())
    time.sleep(0.3)

    plan = {0.06: 5, 0.12: 3, 0.22: 3}
    report: dict = {"keys": {}}
    for key in ("W", "A", "S", "D"):
        key_data = {}
        for hold, reps in plan.items():
            deltas = []
            rates = []
            for _ in range(reps):
                before = read_game_coordinate(box)
                if before is None:
                    print(f"OCR falhou antes de {key}")
                    continue
                gi.tap_key(key, hold)
                time.sleep(0.2)
                after = read_game_coordinate(box)
                if after is None:
                    continue
                dx = after[0] - before[0]
                dy = after[1] - before[1]
                dist = math.hypot(dx, dy)
                deltas.append({"dx": dx, "dy": dy, "norm": dist})
                rates.append(dist / hold)
                time.sleep(0.15)
            key_data[str(hold)] = {
                "deltas": deltas,
                "units_per_sec_mean": round(statistics.fmean(rates), 3) if rates else None,
                "units_per_sec_stdev": round(statistics.pstdev(rates), 3) if len(rates) > 1 else 0.0,
                "n": len(rates),
            }
        report["keys"][key] = key_data

    # linearity check: compare rate at 0.06 vs 0.22
    linearity = {}
    for key, kd in report["keys"].items():
        r06 = (kd.get("0.06") or {}).get("units_per_sec_mean")
        r22 = (kd.get("0.22") or {}).get("units_per_sec_mean")
        if r06 and r22:
            linearity[key] = {"ratio_0.22_over_0.06": round(r22 / r06, 3)}
    report["linearity"] = linearity

    path = OUT / "physics.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
