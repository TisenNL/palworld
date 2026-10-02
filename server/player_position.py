"""Read-only Palworld player-position reader, gated to a verified game build."""

from __future__ import annotations

import ctypes
import hashlib
import math
import os
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
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
READABLE_PROTECTIONS = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}
EXECUTABLE_SECTION = 0x20000000
GWORLD_SIGNATURE_PREFIX = b"\x48\x8b\x05"
GWORLD_SIGNATURE_SUFFIX = b"\xeb\x05"

# This exact build was validated against live player movement.
SUPPORTED_EXECUTABLE_SHA256 = "e590b5e7bfaa3fea40fab1a02cc72c8fc5fd6f8631ef2308e95ac56c25195837"
# Build-specific UE object offsets from GWorld through the local pawn.
WORLD_GAME_INSTANCE_OFFSET = 0x1B8
GAME_INSTANCE_LOCAL_PLAYERS_OFFSET = 0x38
LOCAL_PLAYER_CONTROLLER_OFFSET = 0x30
PLAYER_CONTROLLER_PAWN_OFFSET = 0x330
ACTOR_POINTER_OFFSET = 0x30
FIRST_OBJECT_POINTER_OFFSET = 0x2D0
LOCATION_VECTOR_OFFSET = 0xA18
PALPAGOS_BOUNDS = (-1_099_400.0, 349_400.0, -724_400.0, 724_400.0)
WORLD_TREE_BOUNDS = (347_351.5, 689_148.5, -818_197.0, -476_400.0)
_BUILD_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_BUILD_HASH_LOCK = threading.Lock()
_GWORLD_RVA_CACHE: dict[tuple[str, int, int], Optional[int]] = {}


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


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * 256),
        ("szExePath", wintypes.WCHAR * 260),
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


def _gworld_signature_offsets(data: bytes) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        offset = data.find(GWORLD_SIGNATURE_PREFIX, start)
        if offset < 0:
            return offsets
        if data[offset + 7 : offset + 9] == GWORLD_SIGNATURE_SUFFIX:
            offsets.append(offset)
        start = offset + 1


def _scan_gworld_signature(
    executable,
    raw_offset: int,
    raw_size: int,
    virtual_address: int,
) -> list[int]:
    executable.seek(raw_offset)
    scanned = 0
    carry = b""
    found: list[int] = []
    while scanned < raw_size:
        chunk = executable.read(min(1024 * 1024, raw_size - scanned))
        if not chunk:
            break
        combined = carry + chunk
        previous_scanned = scanned
        for offset in _gworld_signature_offsets(combined):
            section_offset = previous_scanned - len(carry) + offset
            if section_offset + 9 > previous_scanned:
                found.append(virtual_address + section_offset)
                if len(found) > 1:
                    return found
        scanned += len(chunk)
        carry = combined[-8:]
    return found


def _find_gworld_signature_rva(executable_path: Path) -> Optional[int]:
    try:
        stat = executable_path.stat()
    except OSError:
        return None
    cache_key = (str(executable_path).casefold(), stat.st_size, stat.st_mtime_ns)
    with _BUILD_HASH_LOCK:
        if cache_key in _GWORLD_RVA_CACHE:
            return _GWORLD_RVA_CACHE[cache_key]

    matches: list[int] = []
    try:
        with executable_path.open("rb") as executable:
            executable.seek(0x3C)
            dos_header_offset = executable.read(4)
            if len(dos_header_offset) != 4:
                return None
            pe_offset = struct.unpack("<I", dos_header_offset)[0]
            executable.seek(pe_offset)
            pe_header = executable.read(24)
            if len(pe_header) != 24 or pe_header[:4] != b"PE\0\0":
                return None
            section_count = struct.unpack_from("<H", pe_header, 6)[0]
            optional_header_size = struct.unpack_from("<H", pe_header, 20)[0]
            sections_offset = pe_offset + 24 + optional_header_size
            for index in range(section_count):
                executable.seek(sections_offset + index * 40)
                section = executable.read(40)
                if len(section) != 40:
                    return None
                virtual_address = struct.unpack_from("<I", section, 12)[0]
                raw_size = struct.unpack_from("<I", section, 16)[0]
                raw_offset = struct.unpack_from("<I", section, 20)[0]
                characteristics = struct.unpack_from("<I", section, 36)[0]
                if not characteristics & EXECUTABLE_SECTION or raw_size == 0:
                    continue
                matches.extend(
                    _scan_gworld_signature(
                        executable,
                        raw_offset,
                        raw_size,
                        virtual_address,
                    )
                )
                if len(matches) > 1:
                    break
    except (OSError, struct.error):
        return None

    result = matches[0] if len(matches) == 1 else None
    with _BUILD_HASH_LOCK:
        _GWORLD_RVA_CACHE.clear()
        _GWORLD_RVA_CACHE[cache_key] = result
    return result


def _process_module_base(kernel32, pid: int, executable_path: Path) -> Optional[int]:
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Module32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(MODULEENTRY32W),
    ]
    kernel32.Module32FirstW.restype = wintypes.BOOL
    kernel32.Module32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(MODULEENTRY32W),
    ]
    kernel32.Module32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32,
        pid,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        module = MODULEENTRY32W()
        module.dwSize = ctypes.sizeof(module)
        if not kernel32.Module32FirstW(snapshot, ctypes.byref(module)):
            error = ctypes.get_last_error()
            if error in (0, 18):
                return None
            raise ctypes.WinError(error)
        expected_path = os.path.normcase(os.path.abspath(executable_path))
        while True:
            module_path = os.path.normcase(os.path.abspath(module.szExePath))
            if module_path == expected_path:
                return ctypes.cast(module.modBaseAddr, ctypes.c_void_p).value
            if not kernel32.Module32NextW(snapshot, ctypes.byref(module)):
                error = ctypes.get_last_error()
                if error not in (0, 18):
                    raise ctypes.WinError(error)
                return None
    finally:
        kernel32.CloseHandle(snapshot)


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


def _valid_pointer(value: int) -> bool:
    return 0x10000 <= value <= 0x00007FFFFFFFFFFF and value % 8 == 0


def _read_pointer(
    address: int,
    read_memory: Callable[[int, int], Optional[bytes]],
) -> Optional[int]:
    raw = read_memory(address, 8)
    if raw is None or len(raw) != 8:
        return None
    pointer = struct.unpack("<Q", raw)[0]
    return pointer if _valid_pointer(pointer) else None


def _read_local_player_actor_address(
    world_address: int,
    read_memory: Callable[[int, int], Optional[bytes]],
) -> Optional[int]:
    game_instance = _read_pointer(
        world_address + WORLD_GAME_INSTANCE_OFFSET,
        read_memory,
    )
    if game_instance is None:
        return None

    local_players = read_memory(
        game_instance + GAME_INSTANCE_LOCAL_PLAYERS_OFFSET,
        16,
    )
    if local_players is None or len(local_players) != 16:
        return None
    local_players_data, count, capacity = struct.unpack("<Qii", local_players)
    if not _valid_pointer(local_players_data) or not 1 <= count <= capacity <= 8:
        return None

    local_player = _read_pointer(local_players_data, read_memory)
    if local_player is None:
        return None
    player_controller = _read_pointer(
        local_player + LOCAL_PLAYER_CONTROLLER_OFFSET,
        read_memory,
    )
    if player_controller is None:
        return None
    return _read_pointer(
        player_controller + PLAYER_CONTROLLER_PAWN_OFFSET,
        read_memory,
    )


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
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        return _position_status(
            "unsupported",
            error="Live player position requires a 64-bit Python helper",
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

            signature_rva = _find_gworld_signature_rva(executable)
            if signature_rva is None:
                return _position_status(
                    "probe_error",
                    pid=pid,
                    process_found=True,
                    read_access=True,
                    error="Could not locate a unique validated Unreal world signature",
                )
            module_base = _process_module_base(kernel32, pid, executable)
            if module_base is None:
                return _position_status(
                    "probe_error",
                    pid=pid,
                    process_found=True,
                    read_access=True,
                    error="Could not locate the Palworld module in the game process",
                )

            def read_memory(address: int, size: int) -> Optional[bytes]:
                return _read_process_memory(kernel32, handle, address, size)

            instruction = read_memory(module_base + signature_rva, 9)
            if (
                instruction is None
                or instruction[:3] != GWORLD_SIGNATURE_PREFIX
                or instruction[7:9] != GWORLD_SIGNATURE_SUFFIX
            ):
                return _position_status(
                    "unsupported_build",
                    pid=pid,
                    process_found=True,
                    read_access=True,
                    error="The loaded Palworld module does not match its validated world signature",
                )
            displacement = struct.unpack_from("<i", instruction, 3)[0]
            world_global = module_base + signature_rva + 7 + displacement
            world_address = _read_pointer(world_global, read_memory)
            actor_address = (
                _read_local_player_actor_address(world_address, read_memory)
                if world_address is not None
                else None
            )
            if actor_address is None:
                return _position_status(
                    "waiting_for_player",
                    pid=pid,
                    process_found=True,
                    read_access=True,
                    error="Waiting for the local player character to be available",
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
