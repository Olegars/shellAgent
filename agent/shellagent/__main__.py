"""Точка входа демона: python -m shellagent."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from shellagent.server import serve


def _parent_alive() -> bool:
    ppid = os.getppid()
    if ppid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(ppid, 0)
        except OSError:
            return False
        return True
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel.OpenProcess(0x1000, False, ppid)
    if not handle:
        return True
    code = wintypes.DWORD()
    ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel.CloseHandle(handle)
    if not ok:
        return True
    return code.value == 259


def _watch_parent() -> None:
    while True:
        time.sleep(0.5)
        if _parent_alive():
            continue
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(os.getpid())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        os._exit(0)


def main() -> int:
    port = os.environ.get("SHELLA_PORT", "")
    token = os.environ.get("SHELLA_TOKEN", "")
    if not port or not token:
        print("Нужны переменные SHELLA_PORT и SHELLA_TOKEN", file=sys.stderr)
        return 2
    trace = os.environ.get("SHELLA_TRACE_ROOT") or str(os.path.join(os.getcwd(), "traces"))
    threading.Thread(target=_watch_parent, daemon=True).start()
    serve(int(port), token, trace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
