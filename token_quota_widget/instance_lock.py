from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import TextIO


ERROR_ALREADY_EXISTS = 183


class InstanceLock:
    def __init__(
        self,
        name: str = "TokenQuotaWidget",
        *,
        runtime_dir: Path | None = None,
    ) -> None:
        self._handle: int | None = None
        self._file: TextIO | None = None
        if os.name == "nt":
            self._acquire_windows(name)
        else:
            self._acquire_posix(name, runtime_dir)

    def _acquire_windows(self, name: str) -> None:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        create_mutex.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL

        ctypes.set_last_error(0)
        handle = create_mutex(None, False, f"Local\\{name}")
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            close_handle(handle)
            raise RuntimeError("Token 额度组件已经在运行")
        self._handle = handle

    def _acquire_posix(self, name: str, runtime_dir: Path | None) -> None:
        import fcntl

        runtime = runtime_dir or Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = runtime / f"{name}-{os.getuid()}.lock"
        handle = path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise RuntimeError("Token 额度组件已经在运行") from None
        self._file = handle

    def close(self) -> None:
        if self._handle is not None:
            from ctypes import wintypes

            handle = self._handle
            self._handle = None
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = (wintypes.HANDLE,)
            close_handle.restype = wintypes.BOOL
            if not close_handle(handle):
                raise ctypes.WinError(ctypes.get_last_error())

        if self._file is not None:
            import fcntl

            handle = self._file
            self._file = None
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            finally:
                handle.close()
