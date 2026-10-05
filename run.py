"""Start Palworld Checklist + helper. Stop with Ctrl+C."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765
APP_URL = f"http://{HOST}:{PORT}/"


def _npm() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True)


def _powershell(script: Path) -> None:
    if sys.platform != "win32" or not script.is_file():
        return
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=ROOT,
        check=False,
    )


def _needs_npm_ci() -> bool:
    lock = ROOT / "package-lock.json"
    stamp = ROOT / "node_modules" / ".package-lock.json"
    if not stamp.is_file():
        return True
    if not lock.is_file():
        return False
    return lock.stat().st_mtime > stamp.stat().st_mtime


def _ensure_node() -> None:
    if shutil.which("node") is None:
        raise SystemExit("ERROR: Node.js 20 or newer was not found.")


def _ensure_frontend() -> None:
    if _needs_npm_ci():
        print("Installing frontend dependencies...", flush=True)
        _run([_npm(), "ci"])
    print("Building Vue frontend...", flush=True)
    _run([_npm(), "run", "build"])


def _ensure_ocr() -> None:
    probe = subprocess.run(
        [sys.executable, "-c", "import rapidocr_onnxruntime"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if probe.returncode != 0:
        print("Installing local OCR engine on first use...", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "rapidocr-onnxruntime"],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            print("WARNING: OCR engine could not be installed.", flush=True)
    mss_probe = subprocess.run(
        [sys.executable, "-c", "import mss"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if mss_probe.returncode != 0:
        print("Installing mss screen capture...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "mss"],
            cwd=ROOT,
            check=False,
        )


def _open_browser_when_ready() -> None:
    def worker() -> None:
        time.sleep(1.2)
        try:
            urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=5)
            webbrowser.open(APP_URL)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def main() -> int:
    os.chdir(ROOT)
    print(flush=True)
    print("=" * 40, flush=True)
    print(" Palworld Checklist + HUD tooltip", flush=True)
    print("=" * 40, flush=True)
    print(f"Starting server on http://127.0.0.1:{PORT}/", flush=True)
    print("Ctrl+C stops the helper.", flush=True)
    print(flush=True)

    os.environ["PALWORLD_PORT"] = str(PORT)
    _powershell(ROOT / "scripts" / "register-protocol.ps1")
    _powershell(ROOT / "scripts" / "kill-helper.ps1")
    _ensure_node()
    _ensure_frontend()
    _ensure_ocr()
    _open_browser_when_ready()

    from server.coord_tooltip import main as server_main

    try:
        server_main()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed with exit {exc.returncode}", flush=True)
        raise SystemExit(exc.returncode) from exc
