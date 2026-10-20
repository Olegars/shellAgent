"""Поиск собранного шела. Запуск окна вынесен в WinDesktop."""

from __future__ import annotations

import os
from pathlib import Path

EXE_NAMES = {"appsector0451.exe"}
_SKIP_DIRS = {".git", "CMakeFiles", ".venv", "node_modules", "__pycache__"}


def find_shell_exe(shell_path: str, exe_path: str = "") -> str:
    if exe_path:
        path = Path(exe_path)
        if path.is_file():
            return str(path)
        raise FileNotFoundError(f"файл шела не найден: {exe_path}")

    root = Path(shell_path)
    if not root.is_dir():
        raise FileNotFoundError(f"каталог шела не найден: {shell_path}")

    build = root / "build"
    bases = [build, root] if build.is_dir() else [root]
    found: list[Path] = []
    for base in bases:
        for dirpath, dirnames, filenames in os.walk(base):
            rel = Path(dirpath).relative_to(base)
            if len(rel.parts) > 5:
                dirnames.clear()
                continue
            dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRS]
            for filename in filenames:
                if filename.lower() in EXE_NAMES:
                    found.append(Path(dirpath) / filename)
        if found:
            break
    if not found:
        raise FileNotFoundError(
            "не найден appsector0451.exe. Соберите шелл в C:/Qt/compclubshell или укажите путь к exe."
        )
    found.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return str(found[0])
