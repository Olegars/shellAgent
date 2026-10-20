"""Сопоставление новых строк журнала шела с ожидаемым экраном."""

from __future__ import annotations

import re

_QML = re.compile(
    r"(?i)(TypeError|ReferenceError|is not a type|Cannot assign|Unable to assign|"
    r"QQmlApplicationEngine failed|cannot open file)"
)
_FATAL = re.compile(r"\[(CRT|FTL)\]|\bASSERT\b|Fatal")
_WARN_FAIL = re.compile(r"(?i)(\bFAIL\b|\[WRN\].*(error|timeout|не найден))")


def verify(
    log_lines: list[str],
    alive: bool,
    repro: list[str],
    screenshot: str,
    screen: str,
) -> list[dict]:
    bugs: list[dict] = []

    def add(severity: str, title: str, expected: str, actual: str) -> None:
        if len(bugs) >= 5:
            return
        bugs.append(
            {
                "severity": severity,
                "title": title,
                "reproSteps": list(repro),
                "screenshotPath": screenshot,
                "request": {"method": "", "url": screen, "status": 0},
                "expected": expected,
                "actual": actual[:300],
            }
        )

    if not alive:
        add(
            "blocker",
            "Шелл завершился во время прогона",
            "процесс appsector0451 жив до конца сценария",
            "процесс завершился",
        )

    for line in log_lines:
        if _QML.search(line):
            add("major", "Ошибка QML", "экран без ошибок QML", line)
        elif _FATAL.search(line):
            add("blocker", "Критическая ошибка шела", "журнал без CRT/FTL", line)
        elif _WARN_FAIL.search(line):
            add("minor", "Предупреждение шела", "шаг без FAIL в журнале", line)
    return bugs
