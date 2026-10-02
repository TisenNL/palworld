"""Read-only Palworld player-position reader, gated to a verified game build."""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import re
import struct
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

PALWORLD_PROCESS_NAME = "Palworld-Win64-Shipping.exe"
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x00001000
PROCESS_QUERY_INFORMATION = 0x00000400
PROCESS_VM_READ = 0x00000010
ERROR_ACCESS_DENIED = 5
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
READABLE_PROTECTIONS = {0x04, 0x08, 0x40, 0x80}

# This exact build was validated against live Overwolf samples and character movement.
SUPPORTED_EXECUTABLE_SHA256 = "e590b5e7bfaa3fea40fab1a02cc72c8fc5fd6f8631ef2308e95ac56c25195837"
ACTOR_POINTER_OFFSET = 0x30
FIRST_OBJECT_POINTER_OFFSET = 0x2D0
LOCATION_VECTOR_OFFSET = 0xA18
PALPAGOS_BOUNDS = (-1_099_400.0, 349_400.0, -724_400.0, 724_400.0)
WORLD_TREE_BOUNDS = (347_351.5, 689_148.5, -818_197.0, -476_400.0)
OVERWOLF_PLAYER_MESSAGE = "Got first player "
_BUILD_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_BUILD_HASH_LOCK = threading.Lock()


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


def _iter_processes() -> Iterable[tuple[int, str]]:
    if os.name != "nt":
        raise OSError("Palworld process probing requires Windows")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            raise ctypes.WinError(ctypes.get_last_error())

        while True:
            yield entry.th32ProcessID, entry.szExeFile
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error not in (0, 18):  # ERROR_NO_MORE_FILES
                    raise ctypes.WinError(error)
                break
    finally:
        kernel32.CloseHandle(snapshot)


def _can_open_for_read(pid: int) -> tuple[bool, int]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ,
        False,
        pid,
    )
    if not handle:
        return False, ctypes.get_last_error()
    kernel32.CloseHandle(handle)
    return True, 0


def _make_status(status: str, *, pid: Optional[int] = None, error: str = "") -> dict:
    return {
        "ok": True,
        "status": status,
        "processFound": pid is not None,
        "readAccess": status == "ready",
        "pid": pid,
        "error": error,
    }


def _position_status(
    status: str,
    *,
    pid: Optional[int] = None,
    process_found: bool = False,
    read_access: bool = False,
    position: Optional[dict] = None,
    error: str = "",
) -> dict:
    return {
        "ok": True,
        "status": status,
        "processFound": process_found,
        "readAccess": read_access,
        "pid": pid,
        "position": position,
        "error": error,
    }


def _parse_overwolf_actor_address(lines: Iterable[str]) -> Optional[tuple[int, float]]:
    latest: Optional[tuple[datetime, int]] = None
    timestamp_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")
    for line in lines:
        if OVERWOLF_PLAYER_MESSAGE not in line:
            continue
        timestamp_match = timestamp_pattern.match(line)
        if timestamp_match is None:
            continue
        try:
            sample_time = datetime.strptime(timestamp_match.group(1), "%Y-%m-%d %H:%M:%S,%f")
            payload_start = line.index(OVERWOLF_PLAYER_MESSAGE) + len(OVERWOLF_PLAYER_MESSAGE)
            message = json.loads(line[payload_start:])
            address = message["payload"]["address"]
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(address, bool) or not isinstance(address, (int, float)):
            continue
        if not math.isfinite(address) or int(address) != address or address <= 0:
            continue
        if latest is None or sample_time > latest[0]:
            latest = (sample_time, int(address))
    if latest is None:
        return None
    return latest[1], time.mktime(latest[0].timetuple()) + latest[0].microsecond / 1_000_000


def _find_overwolf_actor_address(log_root: Optional[Path] = None) -> Optional[tuple[int, float]]:
    if log_root is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return None
        log_root = Path(local_app_data) / "Overwolf" / "Log" / "Apps" / "Palworld"
    if not log_root.is_dir():
        return None

    lines: list[str] = []
    for path in log_root.glob("background.html*.log"):
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                with path.open("rb") as log_file:
                    log_file.seek(-2 * 1024 * 1024, os.SEEK_END)
                    content = log_file.read().decode("utf-8", errors="replace")
            else:
                content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines.extend(content.splitlines())
    return _parse_overwolf_actor_address(lines)


def _is_supported_executable(path: Path) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    cache_key = (str(path).casefold(), stat.st_size, stat.st_mtime_ns)
    with _BUILD_HASH_LOCK:
        digest = _BUILD_HASH_CACHE.get(cache_key)
        if digest is None:
            hasher = hashlib.sha256()
            with path.open("rb") as executable:
                for chunk in iter(lambda: executable.read(1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
            _BUILD_HASH_CACHE.clear()
            _BUILD_HASH_CACHE[cache_key] = digest
    return digest == SUPPORTED_EXECUTABLE_SHA256


def _process_image_path(kernel32, handle) -> Optional[Path]:
    buffer = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(buffer))
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
        return None
    return Path(buffer.value)


def _process_start_time(kernel32, handle) -> Optional[float]:
    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    creation = FILETIME()
    exit_time = FILETIME()
    kernel_time = FILETIME()
    user_time = FILETIME()
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    if not kernel32.GetProcessTimes(
        handle,
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel_time),
        ctypes.byref(user_time),
    ):
        return None
    ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    return ticks / 10_000_000 - 11_644_473_600


def _read_process_memory(kernel32, handle, address: int, size: int) -> Optional[bytes]:
    if address <= 0 or address > 0x00007FFFFFFFFFFF or size <= 0:
        return None
    information = MEMORY_BASIC_INFORMATION()
    if not kernel32.VirtualQueryEx(
        handle,
        ctypes.c_void_p(address),
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        return None
    protection = information.Protect & 0xFF
    if (
        information.State != MEM_COMMIT
        or protection not in READABLE_PROTECTIONS
        or information.Protect & PAGE_GUARD
    ):
        return None
    region_offset = address - int(information.BaseAddress or 0)
    if size > int(information.RegionSize) - region_offset:
        return None

    buffer = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t()
    if not kernel32.ReadProcessMemory(
        handle,
        ctypes.c_void_p(address),
        buffer,
        size,
        ctypes.byref(bytes_read),
    ) or bytes_read.value != size:
        return None
    return buffer.raw


def _position_zone(x: float, y: float) -> Optional[str]:
    min_x, max_x, min_y, max_y = WORLD_TREE_BOUNDS
    if min_x <= x <= max_x and min_y <= y <= max_y:
        return "world-tree"
    min_x, max_x, min_y, max_y = PALPAGOS_BOUNDS
    if min_x <= x <= max_x and min_y <= y <= max_y:
        return "palpagos"
    return None


def _read_player_position_from_memory(
    actor_address: int,
    read_memory: Callable[[int, int], Optional[bytes]],
) -> Optional[tuple[float, float, float]]:
    first_pointer = read_memory(actor_address + ACTOR_POINTER_OFFSET, 8)
    if first_pointer is None:
        return None
    first_object = struct.unpack("<Q", first_pointer)[0]
    second_pointer = read_memory(first_object + FIRST_OBJECT_POINTER_OFFSET, 8)
    if second_pointer is None:
        return None
    second_object = struct.unpack("<Q", second_pointer)[0]
    vector = read_memory(second_object + LOCATION_VECTOR_OFFSET, 24)
    if vector is None:
        return None
    x, y, z = struct.unpack("<ddd", vector)
    if not all(math.isfinite(value) for value in (x, y, z)):
        return None
    if not -100_000 <= z <= 1_000_000:
        return None
    if _position_zone(x, y) is None:
        return None
    return x, y, z


def _read_player_position(kernel32, handle, actor_address: int) -> Optional[tuple[float, float, float]]:
    return _read_player_position_from_memory(
        actor_address,
        lambda address, size: _read_process_memory(kernel32, handle, address, size),
    )


def probe_palworld_process(
    *,
    process_entries: Optional[Callable[[], Iterable[tuple[int, str]]]] = None,
    read_access: Optional[Callable[[int], tuple[bool, int]]] = None,
) -> dict:
    """Find the game process and check read-only access without reading its memory."""
    if os.name != "nt" and process_entries is None:
        return _make_status("unsupported", error="Process probing is available on Windows only")

    entries = (process_entries or _iter_processes)()
    candidates = [
        pid
        for pid, name in entries
        if name.casefold() == PALWORLD_PROCESS_NAME.casefold()
    ]
    if not candidates:
        return _make_status("not_running")

    check_access = read_access or _can_open_for_read
    access_errors: list[int] = []
    for pid in candidates:
        can_read, error_code = check_access(pid)
        if can_read:
            return _make_status("ready", pid=pid)
        access_errors.append(error_code)

    if all(error == ERROR_ACCESS_DENIED for error in access_errors):
        return _make_status("access_denied", pid=candidates[0], error="Access denied")
    return _make_status(
        "probe_error",
        pid=candidates[0],
        error=f"Could not open the game process (Windows error {access_errors[0]})",
    )


def read_palworld_position() -> dict:
    """Read the validated player location from the supported game build without writing memory."""
    if os.name != "nt":
        return _position_status(
            "unsupported",
            error="Live player position is available on Windows only",
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    candidates = [
        pid
        for pid, name in _iter_processes()
        if name.casefold() == PALWORLD_PROCESS_NAME.casefold()
    ]
    if not candidates:
        return _position_status("not_running", error="Palworld is not running")

    open_errors: list[int] = []
    for pid in candidates:
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ,
            False,
            pid,
        )
        if not handle:
            open_errors.append(ctypes.get_last_error())
            continue
        try:
            executable = _process_image_path(kernel32, handle)
            if executable is None:
                return _position_status(
                    "probe_error",
                    pid=pid,
                    process_found=True,
                    read_access=True,
                    error="Could not identify the game executable",
                )
            if not _is_supported_executable(executable):
                return _position_status(
                    "unsupported_build",
                    pid=pid,
                    process_found=True,
                    read_access=True,
                    error="This Palworld build has not been validated for live position reading",
                )

            actor = _find_overwolf_actor_address()
            if actor is None:
                return _position_status(
                    "waiting_for_overwolf",
                    pid=pid,
                    process_found=True,
                    read_access=True,
                    error="Open the Palworld Overwolf app once to initialize the player reader",
                )
            actor_address, sample_time = actor
            process_start = _process_start_time(kernel32, handle)
            if process_start is not None and sample_time < process_start - 2:
                return _position_status(
                    "waiting_for_overwolf",
                    pid=pid,
                    process_found=True,
                    read_access=True,
                    error="Restart the Palworld Overwolf app to refresh its player reference",
                )

            position = _read_player_position(kernel32, handle, actor_address)
            if position is None:
                return _position_status(
                    "invalid_position",
                    pid=pid,
                    process_found=True,
                    read_access=True,
                    error="The current player reference or coordinates could not be validated",
                )
            x, y, z = position
            return _position_status(
                "ready",
                pid=pid,
                process_found=True,
                read_access=True,
                position={
                    "gameX": x,
                    "gameY": y,
                    "gameZ": z,
                    "mapZone": _position_zone(x, y),
                    "updatedAt": datetime.now().astimezone().isoformat(),
                },
            )
        finally:
            kernel32.CloseHandle(handle)

    if open_errors and all(error == ERROR_ACCESS_DENIED for error in open_errors):
        return _position_status(
            "access_denied",
            pid=candidates[0],
            process_found=True,
            error="Access denied while opening Palworld for read-only access",
        )
    error_code = open_errors[0] if open_errors else 0
    return _position_status(
        "probe_error",
        pid=candidates[0],
        process_found=True,
        error=f"Could not open the game process (Windows error {error_code})",
    )
