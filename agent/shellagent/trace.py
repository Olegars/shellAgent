"""Журнал прогона: события, строки лога шела, баги, снимок знаний."""

from __future__ import annotations

import json
import threading
from pathlib import Path


class Trace:
    def __init__(self, root: Path, run_id: str):
        self.run_id = run_id
        self.dir = root / run_id
        self.shots = self.dir / "shots"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.shots.mkdir(exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.log_path = self.dir / "shell-log.jsonl"
        self.bugs_path = self.dir / "bugs.json"
        self.bugs: list[dict] = []
        self._seq = 0
        self._lock = threading.Lock()

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def shot_path(self, step: int) -> Path:
        return self.shots / f"{step}.png"

    def append_event(self, event: dict) -> None:
        line = json.dumps(event, ensure_ascii=False)
        with self._lock:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def append_log(self, lines: list[str]) -> None:
        if not lines:
            return
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(json.dumps({"line": line}, ensure_ascii=False) + "\n")

    def add_bug(self, bug: dict) -> None:
        with self._lock:
            self.bugs.append(bug)
            self.bugs_path.write_text(
                json.dumps(self.bugs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def write_knowledge(self, knowledge: dict) -> None:
        (self.dir / "knowledge.json").write_text(
            json.dumps(knowledge, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
