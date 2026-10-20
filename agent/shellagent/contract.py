"""Проверка тела POST /runs. Ключ API в эту структуру не сериализуется."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ACTIONS = {
    "click",
    "clickAt",
    "type",
    "press",
    "scroll",
    "wait",
    "done",
    "blocked",
}


@dataclass
class RunConfig:
    shell_path: str
    exe_path: str
    task: str
    max_steps: int
    provider: str
    model: str
    base_url: str
    api_key: str
    allow_login: bool
    allow_launch: bool
    allow_payments: bool
    fidelity: str
    run_id: str = ""
    trace_dir: str = ""

    def __repr__(self) -> str:
        return (
            f"RunConfig(shell={self.shell_path!r}, model={self.model!r}, "
            f"steps={self.max_steps}, fidelity={self.fidelity!r})"
        )


def _bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError("флаг политики должен быть boolean")


def _text(data: dict, key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{key} должен быть строкой")
    return value.strip()


def parse_run_payload(data: object) -> RunConfig:
    if not isinstance(data, dict):
        raise ValueError("тело запроса должно быть объектом")

    shell = _text(data, "shellPath")
    if not shell:
        raise ValueError("shellPath не может быть пустым")
    if not Path(shell).is_dir():
        raise ValueError("каталог шела не найден")

    exe = _text(data, "exePath")
    if exe and not Path(exe).is_file():
        raise ValueError("файл шела не найден")

    task = _text(data, "task")
    if not task:
        raise ValueError("task не может быть пустым")

    if "maxSteps" in data and data["maxSteps"] is not None:
        steps = data["maxSteps"]
        if isinstance(steps, bool) or not isinstance(steps, int):
            raise ValueError("maxSteps должен быть целым числом")
        if steps < 5 or steps > 40:
            raise ValueError("maxSteps вне диапазона 5–40")
    else:
        steps = 25

    llm = data.get("llm")
    if not isinstance(llm, dict):
        raise ValueError("llm должен быть объектом")
    provider = llm.get("provider")
    model = llm.get("model")
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("llm.provider обязателен")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("llm.model обязателен")
    base = llm.get("baseUrl", "")
    if base is None:
        base = ""
    if not isinstance(base, str):
        raise ValueError("llm.baseUrl должен быть строкой")

    policy = data.get("policy") or {}
    if not isinstance(policy, dict):
        raise ValueError("policy должен быть объектом")

    fidelity = data.get("fidelity", "vision")
    if fidelity not in ("vision", "log-only"):
        raise ValueError("fidelity должен быть vision или log-only")

    return RunConfig(
        shell_path=shell,
        exe_path=exe,
        task=task,
        max_steps=steps,
        provider=provider.strip().lower(),
        model=model.strip(),
        base_url=base.strip(),
        api_key="",
        allow_login=_bool(policy.get("allowLogin")),
        allow_launch=_bool(policy.get("allowLaunch")),
        allow_payments=_bool(policy.get("allowPayments")),
        fidelity=fidelity,
    )
