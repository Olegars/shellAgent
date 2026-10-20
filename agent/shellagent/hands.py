"""Руки агента: запуск appsector0451, снимок окна и хвост журнала."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from shellagent.desktop import WinDesktop
from shellagent.locator import find_shell_exe
from shellagent.logtail import LogTail

SHELL_LOG = Path("C:/ShellVideo/logs/shell-debug.log")


@dataclass
class Observation:
    url: str
    title: str
    text: str
    a11y: str
    scale: float
    image: bytes
    log: list[str] = field(default_factory=list)
    alive: bool = True
    image_width: int = 0
    image_height: int = 0


class ShellHands:
    def __init__(self, shell_path: str, exe_path: str = "", desktop: WinDesktop | None = None):
        self.shell_path = shell_path
        self.exe_path = exe_path
        self.desktop = desktop or WinDesktop()
        self.url = ""
        self.scale = 1.0
        self.hwnd = 0
        self.stderr_path = Path("traces") / "shell-stderr.log"
        self._logs: LogTail | None = None
        self._closed = False

    def bind_trace(self, trace_dir: Path) -> None:
        self.stderr_path = Path(trace_dir) / "shell-stderr.log"

    def start(self) -> None:
        self.desktop.enable_dpi()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.desktop.close_process()
        self.hwnd = 0

    def open(self, _target: str = "") -> str:
        try:
            exe = find_shell_exe(self.shell_path, self.exe_path)
        except FileNotFoundError as exc:
            return str(exc)
        image = Path(exe).name
        if self.desktop.image_running(image):
            return (
                f"{image} уже запущен. Закройте шелл перед прогоном, "
                "чтобы агент не трогал чужую сессию."
            )
        self.stderr_path.parent.mkdir(parents=True, exist_ok=True)
        self.stderr_path.write_bytes(b"")
        self._logs = LogTail([SHELL_LOG, self.stderr_path])
        try:
            pid = self.desktop.launch(exe, str(self.stderr_path))
        except OSError as exc:
            return "не удалось запустить шелл: " + str(exc)[:200]
        self.hwnd = self.desktop.wait_window(pid, 20)
        if not self.hwnd:
            self.desktop.close_process()
            return "окно шела не появилось"
        self.url = self.desktop.window_title(self.hwnd) or "SHELL"
        return ""

    def snapshot(self, path: Path) -> Observation:
        alive = self.desktop.process_alive() and self.desktop.is_window(self.hwnd)
        log = self._logs.read_new() if self._logs else []
        title = ""
        image = b""
        scale = self.scale or 1.0
        width = 0
        height = 0
        a11y = ""
        if alive:
            title = self.desktop.window_title(self.hwnd) or self.url
            self.url = title
            try:
                image, scale, width, height = self.desktop.capture(self.hwnd)
                self.scale = scale
            except Exception as exc:
                log.append(f"снимок: {exc}")
            a11y = self.desktop.accessibility(self.hwnd)
        if image:
            path.write_bytes(image)
        text = "\n".join([title, *log[-40:]])
        return Observation(
            url=self.url or title,
            title=title,
            text=text[:8000],
            a11y=a11y[:4000],
            scale=scale,
            image=image,
            log=log,
            alive=alive,
            image_width=width,
            image_height=height,
        )

    def perform(self, action: dict) -> str:
        kind = action.get("action")
        try:
            if kind == "click":
                name = str(action.get("name") or "")
                if name and self.desktop.click_name(self.hwnd, name):
                    time.sleep(0.25)
                    return ""
                return "not_found"
            if kind == "clickAt":
                scale = self.scale or 1
                x = float(action.get("x") or 0) / scale
                y = float(action.get("y") or 0) / scale
                self.desktop.click(self.hwnd, x, y)
                time.sleep(0.25)
                return ""
            if kind == "type":
                self.desktop.type_text(str(action.get("text") if action.get("text") is not None else ""))
                return ""
            if kind == "press":
                self.desktop.press(str(action.get("key") or "Enter"))
                return ""
            if kind == "scroll":
                delta = int(action.get("y") if action.get("y") is not None else action.get("dy") or -120)
                self.desktop.scroll(self.hwnd, delta)
                return ""
            if kind == "wait":
                time.sleep(min(3.0, max(0.0, float(action.get("ms") or 300) / 1000.0)))
                return ""
        except Exception as exc:
            message = str(exc).lower()
            if kind in {"click", "type"} or "неизвестная клавиша" in message:
                return "not_found" if kind in {"click", "type"} else str(exc)[:240]
            return str(exc)[:240]
        return "неизвестное действие"
