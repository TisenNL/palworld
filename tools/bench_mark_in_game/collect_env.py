#!/usr/bin/env python3
"""Collect hardware / runtime environment into .cache/timing/env.json."""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache" / "timing"
sys.path.insert(0, str(ROOT))


def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return (r.stdout or "").strip()
    except Exception as exc:
        return f"error:{exc}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "python": sys.version,
        "platform": platform.platform(),
        "os": _ps("(Get-CimInstance Win32_OperatingSystem).Caption + ' ' + (Get-CimInstance Win32_OperatingSystem).Version"),
        "cpu": _ps("(Get-CimInstance Win32_Processor | Select-Object -First 1).Name"),
        "cpu_cores": _ps("(Get-CimInstance Win32_Processor | Select-Object -First 1).NumberOfCores"),
        "cpu_logical": _ps("(Get-CimInstance Win32_Processor | Select-Object -First 1).NumberOfLogicalProcessors"),
        "gpu": _ps("(Get-CimInstance Win32_VideoController).Name -join ' | '"),
        "ram_bytes": _ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"),
    }
    try:
        import onnxruntime as ort

        so = ort.SessionOptions()
        data["onnxruntime"] = {
            "version": ort.__version__,
            "providers": ort.get_available_providers(),
            "intra_op_num_threads": so.intra_op_num_threads,
            "inter_op_num_threads": so.inter_op_num_threads,
        }
    except Exception as exc:
        data["onnxruntime"] = {"error": str(exc)}
    try:
        import rapidocr_onnxruntime as r

        data["rapidocr"] = {"module": getattr(r, "__file__", "?"), "version": getattr(r, "__version__", "?")}
    except Exception as exc:
        data["rapidocr"] = {"error": str(exc)}
    try:
        from server.game_marker_automation import largest_monitor_bounds, monitor_cache_key

        data["largest_monitor"] = list(largest_monitor_bounds())
        data["monitor_cache_key"] = monitor_cache_key()
    except Exception as exc:
        data["largest_monitor"] = {"error": str(exc)}
    data["notes"] = {
        "game_display_mode": "PENDENTE: borderless/fullscreen (preencher manualmente)",
        "monitor_refresh_hz": "PENDENTE",
        "monitor_count": "PENDENTE",
    }
    path = OUT / "env.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
