"""Окно Windows: снимок, клик и ввод. На других ОС методы запуска недоступны."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from shellagent.imageutil import bgra_to_rgba, encode_png, fit_rgba

_VK = {
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}


class _Api:
    ready = False
    ctypes = None
    wintypes = None
    user32 = None
    gdi32 = None
    kernel32 = None
    enum_proc = None


def _api():
    if os.name != "nt":
        raise RuntimeError("управление окном шела доступно только в Windows")
    if _Api.ready:
        return _Api
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_long, ctypes.c_size_t]
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.BitBlt.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    _Api.ready = True
    _Api.ctypes = ctypes
    _Api.wintypes = wintypes
    _Api.user32 = user32
    _Api.gdi32 = gdi32
    _Api.kernel32 = kernel32
    _Api.enum_proc = enum_proc
    return _Api


def _win32():
    api = _api()
    return api.ctypes, api.wintypes


class WinDesktop:
    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._stderr = None
        self._dpi = False

    def image_running(self, image: str) -> bool:
        try:
            output = subprocess.check_output(
                ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
                text=True,
                errors="replace",
                timeout=8,
            )
        except (subprocess.SubprocessError, OSError):
            return False
        return image.lower() in output.lower()

    def launch(self, exe: str, stderr_path: str) -> int:
        path = Path(exe)
        log_path = Path(stderr_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._stderr = log_path.open("ab")
        env = os.environ.copy()
        env["QT_ACCESSIBILITY"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        self._proc = subprocess.Popen(
            [str(path)],
            cwd=str(path.parent),
            env=env,
            stdout=self._stderr,
            stderr=subprocess.STDOUT,
        )
        return int(self._proc.pid)

    def close_process(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None

    def process_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def enable_dpi(self) -> None:
        if self._dpi or os.name != "nt":
            return
        ctypes, wintypes = _win32()
        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                ctypes.windll.user32.SetProcessDPIAware()
        self._dpi = True

    def wait_window(self, pid: int, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            hwnd = self._largest_window(pid)
            if hwnd:
                return hwnd
            time.sleep(0.25)
        return 0

    def is_window(self, hwnd: int) -> bool:
        if not hwnd or os.name != "nt":
            return False
        ctypes, wintypes = _win32()
        return bool(ctypes.windll.user32.IsWindow(wintypes.HWND(hwnd)))

    def window_title(self, hwnd: int) -> str:
        ctypes, wintypes = _win32()
        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(wintypes.HWND(hwnd), buf, length + 1)
        return buf.value

    def capture(self, hwnd: int) -> tuple[bytes, float, int, int]:
        ctypes, wintypes = _win32()
        self.enable_dpi()
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        rect = wintypes.RECT()
        if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            raise RuntimeError("не удалось прочитать размер окна")
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            raise RuntimeError("окно шела имеет нулевой размер")

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

        hwnd_ref = wintypes.HWND(hwnd)
        hdc = user32.GetWindowDC(hwnd_ref)
        if not hdc:
            raise RuntimeError("не удалось получить контекст окна")
        mem = gdi32.CreateCompatibleDC(hdc)
        bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
        old = gdi32.SelectObject(mem, bitmap)
        try:
            if not gdi32.BitBlt(mem, 0, 0, width, height, hdc, 0, 0, 0x00CC0020):
                raise RuntimeError("не удалось снять кадр окна")
            gdi32.SelectObject(mem, old)
            old = None
            info = BITMAPINFO()
            info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            info.bmiHeader.biWidth = width
            info.bmiHeader.biHeight = -height
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = 0
            raw = ctypes.create_string_buffer(width * height * 4)
            rows = gdi32.GetDIBits(mem, bitmap, 0, height, raw, ctypes.byref(info), 0)
            if rows == 0:
                raise RuntimeError("не удалось прочитать пиксели окна")
        finally:
            if old:
                gdi32.SelectObject(mem, old)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if mem:
                gdi32.DeleteDC(mem)
            user32.ReleaseDC(hwnd_ref, hdc)

        rgba, image_w, image_h, scale = fit_rgba(bgra_to_rgba(raw.raw), width, height)
        return encode_png(image_w, image_h, rgba), scale, image_w, image_h

    def click(self, hwnd: int, x: float, y: float) -> None:
        ctypes, wintypes = _win32()
        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        self._focus(hwnd)
        user32.SetCursorPos(int(rect.left + x), int(rect.top + y))
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    def click_name(self, hwnd: int, name: str) -> bool:
        if not name:
            return False
        try:
            import uiautomation as auto
        except ImportError:
            return False
        try:
            root = auto.ControlFromHandle(hwnd)
            target = root.Control(searchDepth=12, Name=name)
            if not target.Exists(0.4):
                return False
            target.Click()
            return True
        except Exception:
            return False

    def accessibility(self, hwnd: int) -> str:
        try:
            import uiautomation as auto
        except ImportError:
            return ""
        try:
            root = auto.ControlFromHandle(hwnd)
            lines: list[str] = []
            for item in root.GetChildren()[:50]:
                label = (item.Name or "").strip()
                if label:
                    lines.append(f"{item.ControlTypeName} {label}")
            return "\n".join(lines)[:4000]
        except Exception:
            return ""

    def type_text(self, text: str) -> None:
        for char in text:
            self._send_unicode(char)

    def press(self, key: str) -> None:
        vk = _VK.get(key.strip().lower())
        if vk is None:
            raise RuntimeError(f"неизвестная клавиша: {key}")
        self._send_vk(vk)

    def scroll(self, hwnd: int, delta: int) -> None:
        ctypes, wintypes = _win32()
        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        self._focus(hwnd)
        user32.SetCursorPos((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
        user32.mouse_event(0x0800, 0, 0, int(delta), 0)

    def _largest_window(self, pid: int) -> int:
        api = _api()
        ctypes, wintypes = api.ctypes, api.wintypes
        user32 = api.user32
        found: list[tuple[int, int]] = []

        @api.enum_proc
        def visit(hwnd, _lparam):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value != pid or not user32.IsWindowVisible(hwnd):
                return True
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
            if area > 0:
                found.append((area, int(hwnd)))
            return True

        user32.EnumWindows(visit, 0)
        if not found:
            return 0
        found.sort(reverse=True)
        return found[0][1]

    def _focus(self, hwnd: int) -> None:
        ctypes, wintypes = _win32()
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd_ref = wintypes.HWND(hwnd)
        user32.ShowWindow(hwnd_ref, 9)
        foreground = user32.GetForegroundWindow()
        current = kernel32.GetCurrentThreadId()
        owner = wintypes.DWORD()
        other = user32.GetWindowThreadProcessId(foreground, ctypes.byref(owner))
        user32.AttachThreadInput(current, other, True)
        user32.SetForegroundWindow(hwnd_ref)
        user32.AttachThreadInput(current, other, False)

    def _send_unicode(self, char: str) -> None:
        ctypes, wintypes = _win32()
        user32 = ctypes.windll.user32

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT)]

        flags_down = 0x0004
        flags_up = 0x0004 | 0x0002
        inputs = (INPUT * 2)(
            INPUT(1, KEYBDINPUT(0, ord(char), flags_down, 0, 0)),
            INPUT(1, KEYBDINPUT(0, ord(char), flags_up, 0, 0)),
        )
        user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))

    def _send_vk(self, vk: int) -> None:
        ctypes, wintypes = _win32()
        user32 = ctypes.windll.user32

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT)]

        inputs = (INPUT * 2)(
            INPUT(1, KEYBDINPUT(vk, 0, 0, 0, 0)),
            INPUT(1, KEYBDINPUT(vk, 0, 0x0002, 0, 0)),
        )
        user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
