#!/usr/bin/env python3
"""Run 10 Mark-in-game dry-runs (5 far, 5 near) via the local helper HTTP API."""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache" / "timing" / "batch_10_runs.json"


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 30.0):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_health(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            http_json("GET", "/health")
            return
        except Exception:
            time.sleep(0.4)
    raise SystemExit("helper não respondeu em /health")


def read_coord(timeout: float = 25.0) -> tuple[int, int]:
    http_json("POST", "/ocr-select", {})
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = http_json("GET", "/ocr-state")
        if st.get("status") == "copied" and st.get("text"):
            a, b = str(st["text"]).split(",", 1)
            return int(a.strip()), int(b.strip())
        if st.get("status") == "error":
            raise RuntimeError(st.get("error") or "OCR error")
        time.sleep(0.25)
    raise TimeoutError("OCR timeout")


def wait_marker_done(timeout: float = 180.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = http_json("GET", "/game-marker/state")
        if not last.get("active") and last.get("status") in ("completed", "error", "cancelled", "idle"):
            if last.get("status") == "idle" and last.get("message") == "":
                time.sleep(0.3)
                continue
            return last
        time.sleep(0.35)
    raise TimeoutError(f"marker timeout: {last}")


def start_mark(x: int, y: int, dry_run: bool = True) -> None:
    http_json("POST", "/game-marker/start", {"x": x, "y": y, "dryRun": dry_run})


def main() -> int:
    wait_health()
    # Ensure Palworld is focused before OCR (helper restart often leaves terminal focused).
    try:
        sys.path.insert(0, str(ROOT))
        from server.game_marker_automation import WindowsGameInput

        WindowsGameInput().focus_game()
        time.sleep(0.4)
    except Exception as exc:
        print(f"aviso focus: {exc}", flush=True)

    print("Lendo coordenada atual...", flush=True)
    try:
        cur = read_coord()
    except Exception as exc:
        print(f"OCR inicial falhou: {exc}", flush=True)
        return 2
    print(f"Atual: {cur}", flush=True)

    # offsets in map units
    far_offsets = [
        (160, 0),
        (-160, 0),
        (0, 160),
        (0, -160),
        (120, 120),
    ]
    near_offsets = [
        (20, 0),
        (-20, 0),
        (0, 18),
        (0, -18),
        (12, 12),
    ]

    results = []
    plan = [("far", o) for o in far_offsets] + [("near", o) for o in near_offsets]

    for i, (kind, (dx, dy)) in enumerate(plan, 1):
        print(f"\n=== Run {i}/10 ({kind}) ===", flush=True)
        try:
            cur = read_coord()
        except Exception as exc:
            print(f"OCR pré-run falhou: {exc}", flush=True)
            results.append({"i": i, "kind": kind, "error": f"ocr:{exc}"})
            continue
        target = (cur[0] + dx, cur[1] + dy)
        dist = math.hypot(dx, dy)
        print(f"from {cur} -> {target} (delta={dist:.1f} u)", flush=True)
        t0 = time.perf_counter()
        try:
            start_mark(target[0], target[1], dry_run=True)
            st = wait_marker_done()
            elapsed = (time.perf_counter() - t0) * 1000.0
            row = {
                "i": i,
                "kind": kind,
                "from": list(cur),
                "target": list(target),
                "delta_u": round(dist, 2),
                "wall_ms": round(elapsed, 1),
                "status": st.get("status"),
                "message": st.get("message"),
                "error": st.get("error"),
                "final": st.get("current"),
                "distanceMeters": st.get("distanceMeters"),
            }
            print(f"done status={row['status']} wall={row['wall_ms']:.0f}ms", flush=True)
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000.0
            row = {
                "i": i,
                "kind": kind,
                "from": list(cur),
                "target": list(target),
                "delta_u": round(dist, 2),
                "wall_ms": round(elapsed, 1),
                "error": str(exc),
            }
            print(f"FAIL {exc}", flush=True)
            try:
                http_json("POST", "/game-marker/cancel", {})
            except Exception:
                pass
            time.sleep(1.0)
        results.append(row)
        time.sleep(0.8)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nBatch summary -> {OUT}", flush=True)
    ok = sum(1 for r in results if r.get("status") == "completed")
    print(f"completed={ok}/{len(results)}", flush=True)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
