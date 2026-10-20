"""Хвост журнала шела: читаются только байты, появившиеся после старта прогона."""

from __future__ import annotations

from pathlib import Path


class LogTail:
    def __init__(self, paths: list[Path]):
        self.paths = list(paths)
        self.pos: dict[str, int] = {}
        for path in self.paths:
            self.pos[str(path)] = path.stat().st_size if path.exists() else 0

    def read_new(self) -> list[str]:
        lines: list[str] = []
        for path in self.paths:
            key = str(path)
            if not path.exists():
                continue
            size = path.stat().st_size
            start = self.pos.get(key, 0)
            if size < start:
                start = 0
            if size == start:
                continue
            with path.open("rb") as handle:
                handle.seek(start)
                data = handle.read()
            self.pos[key] = start + len(data)
            text = data.decode("utf-8", errors="replace")
            lines.extend(line.strip() for line in text.splitlines() if line.strip())
        return lines
