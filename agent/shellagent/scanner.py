"""Разбор каталога шела: экраны QML и имена Q_INVOKABLE, без значений секретов."""

from __future__ import annotations

import re
from pathlib import Path

from shellagent.redact import secret_names_from_env

_LABEL = re.compile(r'(?:text|title|placeholderText)\s*:\s*"([^"\\]{1,48})"')
_OBJECT = re.compile(r'objectName\s*:\s*"([^"]+)"')
_INVOKE = re.compile(r"Q_INVOKABLE\s+.+?\s+(\w+)\s*\(")


def _screen(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    labels: list[str] = []
    for match in _LABEL.finditer(text):
        label = match.group(1).strip()
        if not label or label.startswith("#") or label.startswith("qrc:"):
            continue
        if label not in labels:
            labels.append(label)
        if len(labels) >= 12:
            break
    names: list[str] = []
    for match in _OBJECT.finditer(text):
        name = match.group(1).strip()
        if name and name not in names:
            names.append(name)
    return {
        "file": path.relative_to(root).as_posix(),
        "objectNames": names[:20],
        "labels": labels,
    }


def _invokables(path: Path) -> list[str]:
    found: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if "Q_INVOKABLE" not in line:
            continue
        match = _INVOKE.search(line)
        if match:
            found.append(match.group(1))
    return found


def scan_repository(root: Path) -> dict:
    screens = [_screen(path, root) for path in sorted(root.glob("*.qml"))]
    names: list[str] = []
    src = root / "src"
    if src.is_dir():
        for header in sorted(src.rglob("*.h")):
            for name in _invokables(header):
                if name not in names:
                    names.append(name)
    secrets: list[str] = []
    ini = root / "config.ini"
    if ini.is_file():
        secrets = list(dict.fromkeys(secret_names_from_env(ini.read_text(encoding="utf-8", errors="replace"))))
    return {
        "screens": screens,
        "invokables": names[:80],
        "secretsToRedact": secrets,
    }


def knowledge_for_prompt(knowledge: dict) -> str:
    lines: list[str] = []
    for screen in (knowledge.get("screens") or [])[:24]:
        objects = ", ".join(screen.get("objectNames") or []) or "—"
        labels = ", ".join(screen.get("labels") or []) or "—"
        lines.append(f"- {screen.get('file')}: объекты [{objects}] подписи [{labels}]")
    methods = ", ".join(knowledge.get("invokables") or [])
    if methods:
        lines.append("Методы оболочки: " + methods[:700])
    return "\n".join(lines)
