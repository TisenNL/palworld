#!/usr/bin/env python3
"""ONNX Runtime / RapidOCR configuration notes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache" / "timing"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    info: dict = {"gil_contention": [
        "RapidOCR roda sob OcrSelector._recognition_lock (serializa OCR).",
        "O mesmo processo Python serve HTTP (ThreadingHTTPServer) e Tkinter overlay.",
        "GameMarkerController roda em thread daemon; OCR é chamado dessa thread.",
        "Inferência ONNX CPU compete com o jogo (GPU dedicada não usada pelo ONNX neste setup).",
    ]}
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        so = ort.SessionOptions()
        info["onnxruntime"] = {
            "version": ort.__version__,
            "providers": providers,
            "has_cuda": any("CUDA" in p for p in providers),
            "has_directml": any("Dml" in p or "DirectML" in p for p in providers),
            "has_azure": any("Azure" in p for p in providers),
            "intra_op_num_threads": so.intra_op_num_threads,
            "inter_op_num_threads": so.inter_op_num_threads,
        }
    except Exception as exc:
        info["onnxruntime"] = {"error": str(exc)}
    path = OUT / "onnx_info.json"
    path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
