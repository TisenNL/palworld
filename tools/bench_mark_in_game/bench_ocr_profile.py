#!/usr/bin/env python3
"""Profile one OCR call (fast path) — uses live ROI or .cache/ocr-debug/last-capture.png."""
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
    from PIL import Image, ImageGrab
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    from server.coord_tooltip import (
        game_coordinate_box,
        normalize_coordinate_text,
        prepare_focused_coordinate_images,
        prepare_white_text_images,
    )

    debug = ROOT / ".cache" / "ocr-debug" / "last-capture.png"
    source = "live"
    t_cap = time.perf_counter()
    if "--from-file" in sys.argv and debug.is_file():
        image = Image.open(debug).convert("RGB")
        source = str(debug)
        capture_ms = 0.0
    else:
        box = game_coordinate_box()
        image = ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")
        capture_ms = (time.perf_counter() - t_cap) * 1000.0
        image.save(ROOT / ".cache" / "ocr-debug" / "bench-capture.png")

    engine = RapidOCR(use_text_det=False, use_angle_cls=False)
    # warmup
    engine(np.asarray(image.resize((64, 32))))

    t_pre = time.perf_counter()
    focused = prepare_focused_coordinate_images(image)[5:10]
    white = prepare_white_text_images(image)
    fallback = [white[i] for i in (0, 3, 4)]
    preproc_ms = (time.perf_counter() - t_pre) * 1000.0

    variants = []
    votes: dict[str, tuple[int, float]] = {}
    inference_ms = 0.0
    for stage, imgs in (("focused", focused), ("white", fallback)):
        for img in imgs:
            t0 = time.perf_counter()
            result, _ = engine(np.asarray(img))
            dt = (time.perf_counter() - t0) * 1000.0
            inference_ms += dt
            parts = [str(item[1]).strip() for item in (result or []) if len(item) > 1]
            raw = " ".join(p for p in parts if p).strip()
            cand = normalize_coordinate_text(raw)
            conf = 0.0
            if result:
                conf = sum(float(item[2]) for item in result if len(item) > 2) / max(1, len(result))
            variants.append({"stage": stage, "raw": raw, "candidate": cand, "confidence": conf, "ms": round(dt, 3)})
            if cand:
                c, s = votes.get(cand, (0, 0.0))
                votes[cand] = (c + 1, s + conf)

    winner = None
    if votes:
        winner = max(votes.items(), key=lambda kv: (kv[1][0], kv[1][1]))

    first_ok = next((v for v in variants if v["candidate"]), None)
    payload = {
        "source": source,
        "image_size": list(image.size),
        "capture_ms": round(capture_ms, 3),
        "preproc_ms": round(preproc_ms, 3),
        "inference_ms": round(inference_ms, 3),
        "total_ms": round(capture_ms + preproc_ms + inference_ms, 3),
        "variants_count": len(variants),
        "variants": variants,
        "votes": {k: {"count": v[0], "score_sum": v[1]} for k, v in votes.items()},
        "winner": winner[0] if winner else None,
        "first_variant_candidate": first_ok["candidate"] if first_ok else None,
        "first_variant_won": bool(first_ok and winner and first_ok["candidate"] == winner[0]),
    }
    path = OUT / "ocr_profile.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
