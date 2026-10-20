"""Цикл observe → decide → act → verify с лимитом шагов и остановкой при зацикливании."""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

from shellagent.hands import Observation
from shellagent.llm import Cancelled, LlmAdapter, StepTimeout, parse_model_json
from shellagent.policy import rejection_reason
from shellagent.redact import redact_text
from shellagent.scanner import knowledge_for_prompt, scan_repository
from shellagent.trace import Trace
from shellagent.verifier import verify


def action_signature(action: dict) -> tuple[str, str]:
    kind = str(action.get("action") or "")
    if kind == "clickAt":
        target = f"{action.get('x')},{action.get('y')}:{action.get('name', '')}"
    elif kind == "press":
        target = str(action.get("key") or "")
    elif kind == "scroll":
        target = str(action.get("y") if action.get("y") is not None else "")
    elif kind == "type":
        target = str(action.get("name") or "")
    else:
        target = str(action.get("name") or action.get("selector") or "")
    return kind, target


def describe_action(action: dict) -> str:
    kind, target = action_signature(action)
    if kind == "done":
        return "done: " + str(action.get("summary") or "")
    if kind == "blocked":
        return "blocked: " + str(action.get("reason") or "")
    if kind == "type":
        return f"type {target}".strip()
    return f"{kind} {target}".strip()


def build_user_prompt(
    task: str,
    shell_path: str,
    knowledge_text: str,
    screen: str,
    page_text: str,
    a11y: str,
    history: list[str],
    scale: float,
    fidelity: str,
    policy: dict,
    image_width: int = 0,
    image_height: int = 0,
    names: list[str] | None = None,
    values: list[str] | None = None,
) -> str:
    safe_page = redact_text(page_text or "", names, values)[:4000]
    safe_a11y = redact_text(a11y or "", names, values)[:4000]
    history_text = "\n".join(redact_text(item, names, values) for item in history[-8:])
    vision = "Скриншот приложен." if fidelity == "vision" else "Скриншота нет, решай по заголовку и журналу."
    return (
        f"Задача: {redact_text(task, names, values)}\n"
        f"Каталог шела: {shell_path}\n"
        f"Политика: login={bool(policy.get('allowLogin'))} "
        f"launch={bool(policy.get('allowLaunch'))} "
        f"payments={bool(policy.get('allowPayments'))}\n"
        f"Масштаб скриншота: {scale}. Кадр: {image_width}x{image_height}. {vision}\n"
        f"Окно: {screen or 'ещё не открыто'}\n"
        f"Экраны и методы:\n{knowledge_text or 'нет'}\n"
        f"Заголовок и новый журнал:\n{safe_page or 'пусто'}\n"
        f"Дерево доступности:\n{safe_a11y or 'пусто'}\n"
        f"Последние действия:\n{history_text or 'нет'}\n"
    )


def _empty_knowledge() -> dict:
    return {"screens": [], "invokables": [], "secretsToRedact": []}


def run_loop(
    config,
    emit,
    cancel: threading.Event,
    hands,
    trace: Trace,
    llm: LlmAdapter,
    on_secrets=None,
) -> None:
    names: list[str] = []
    values = [config.api_key] if config.api_key else []
    knowledge = _load_knowledge(config, emit, names, on_secrets, trace)
    if knowledge is None:
        return
    bind = getattr(hands, "bind_trace", None)
    if bind:
        bind(trace.dir)
    try:
        hands.start()
    except Exception as exc:
        emit({"kind": "error", "step": 0, "message": redact_text(str(exc), values=values), "url": ""})
        hands.close()
        return

    label = config.exe_path or config.shell_path
    try:
        opened = hands.open(label)
        emit({"kind": "action", "step": 0, "message": "open " + label, "url": label})
        if opened:
            emit({"kind": "error", "step": 0, "message": opened, "url": label})
            return

        fidelity = config.fidelity
        history: list[str] = [f"open {label}"]
        repro = [f"Открыть {label}"]
        last_obs = None
        obs_repeat = 0
        last_sig = None
        action_repeat = 0
        policy = {
            "allowLogin": config.allow_login,
            "allowLaunch": config.allow_launch,
            "allowPayments": config.allow_payments,
        }
        hint = knowledge_for_prompt(knowledge)

        for step in range(1, config.max_steps + 1):
            if cancel.is_set():
                emit({"kind": "status", "step": step, "message": "cancelled", "url": getattr(hands, "url", "")})
                return
            shot = trace.shot_path(step)
            obs: Observation = hands.snapshot(shot)
            digest = hashlib.sha256(obs.image).hexdigest()
            marker = (obs.url, digest, obs.alive)
            obs_repeat = obs_repeat + 1 if marker == last_obs else 1
            last_obs = marker
            emit(
                {
                    "kind": "observation",
                    "step": step,
                    "message": f"scale={obs.scale}",
                    "screenshotPath": str(shot) if obs.image else "",
                    "url": obs.url,
                }
            )
            if not obs.alive:
                _report_bugs(trace, emit, verify([], False, repro, str(shot), obs.url), names, values, step, shot, obs.url)
                return
            if obs_repeat >= 3:
                emit(
                    {
                        "kind": "error",
                        "step": step,
                        "message": "stuck: одинаковый экран",
                        "screenshotPath": str(shot) if obs.image else "",
                        "url": obs.url,
                    }
                )
                return

            prompt = build_user_prompt(
                config.task,
                config.shell_path,
                hint,
                obs.url,
                obs.text,
                obs.a11y,
                history,
                obs.scale,
                fidelity,
                policy,
                obs.image_width,
                obs.image_height,
                names,
                values,
            )
            image = obs.image if fidelity == "vision" and obs.image else None
            started = time.monotonic()
            try:
                raw = llm.complete(prompt, image)
            except Cancelled:
                emit({"kind": "status", "step": step, "message": "cancelled", "url": obs.url})
                return
            except StepTimeout:
                emit({"kind": "error", "step": step, "message": "таймаут шага", "url": obs.url})
                return
            except RuntimeError as exc:
                if image is not None and "HTTP 400" in str(exc):
                    fidelity = "log-only"
                    emit({"kind": "status", "step": step, "message": "fidelity: log-only", "url": obs.url})
                    try:
                        raw = llm.complete(prompt, None)
                    except Cancelled:
                        emit({"kind": "status", "step": step, "message": "cancelled", "url": obs.url})
                        return
                    except StepTimeout:
                        emit({"kind": "error", "step": step, "message": "таймаут шага", "url": obs.url})
                        return
                    except Exception as inner:
                        emit({"kind": "error", "step": step, "message": redact_text(str(inner), names, values), "url": obs.url})
                        return
                else:
                    emit({"kind": "error", "step": step, "message": redact_text(str(exc), names, values), "url": obs.url})
                    return
            except Exception as exc:
                emit({"kind": "error", "step": step, "message": redact_text(str(exc), names, values), "url": obs.url})
                return

            elapsed = time.monotonic() - started
            action = parse_model_json(raw)
            thought = str(action.get("thought") or "") if action else ""
            emit(
                {
                    "kind": "thought",
                    "step": step,
                    "message": f"{elapsed:.1f}s {redact_text(thought, names, values)}".strip(),
                    "screenshotPath": str(shot) if obs.image else "",
                    "url": obs.url,
                }
            )
            if action is None:
                action = {"action": "wait", "ms": 0}
                history.append("invalid")
                emit({"kind": "observation", "step": step, "message": "модель вернула не действие", "url": obs.url})
                sig = ("invalid", "")
            else:
                sig = action_signature(action)
            action_repeat = action_repeat + 1 if sig == last_sig else 1
            last_sig = sig
            if action_repeat >= 5:
                emit(
                    {
                        "kind": "error",
                        "step": step,
                        "message": "stuck: повторяющееся действие",
                        "screenshotPath": str(shot) if obs.image else "",
                        "url": obs.url,
                    }
                )
                return

            kind = action.get("action")
            if kind == "done":
                emit(
                    {
                        "kind": "done",
                        "step": step,
                        "message": redact_text(str(action.get("summary") or ""), names, values),
                        "url": obs.url,
                    }
                )
                return
            if kind == "blocked":
                emit(
                    {
                        "kind": "action",
                        "step": step,
                        "message": "blocked: " + redact_text(str(action.get("reason") or ""), names, values),
                        "url": obs.url,
                    }
                )
                return

            reason = rejection_reason(action, policy)
            if reason:
                emit({"kind": "action", "step": step, "message": "blocked: " + reason, "screenshotPath": str(shot) if obs.image else "", "url": obs.url})
                return

            result = hands.perform(action)
            step_label = describe_action(action)
            history.append(step_label)
            repro.append(step_label)
            emit(
                {
                    "kind": "action",
                    "step": step,
                    "message": step_label,
                    "screenshotPath": str(shot) if obs.image else "",
                    "url": getattr(hands, "url", obs.url),
                }
            )
            if result == "not_found":
                note = "элемент не найден, укажи clickAt с координатами кадра и подписью в name"
                history.append(note)
                emit({"kind": "observation", "step": step, "message": note, "url": obs.url})
                continue
            if result:
                emit({"kind": "error", "step": step, "message": result, "url": obs.url})
                return

            fresh = hands.snapshot(shot)
            trace.append_log(fresh.log)
            bugs = verify(fresh.log, fresh.alive, repro, str(shot) if fresh.image else "", fresh.url)
            _report_bugs(trace, emit, bugs, names, values, step, shot, fresh.url)
            if not fresh.alive:
                return
        emit({"kind": "status", "step": config.max_steps, "message": "stopped", "url": getattr(hands, "url", "")})
    finally:
        hands.close()


def _report_bugs(trace, emit, bugs, names, values, step, shot, url) -> None:
    for bug in bugs:
        bug["id"] = f"b{len(trace.bugs) + 1}"
        bug["actual"] = redact_text(str(bug.get("actual") or ""), names, values)
        trace.add_bug(bug)
        emit(
            {
                "kind": "bug",
                "step": step,
                "message": bug["title"],
                "screenshotPath": str(shot),
                "url": url,
            }
        )


def _load_knowledge(config, emit, names: list[str], on_secrets, trace: Trace):
    root = Path(config.shell_path)
    if not root.is_dir():
        emit({"kind": "error", "step": 0, "message": "каталог шела не найден", "url": ""})
        return None
    knowledge = scan_repository(root)
    emit(
        {
            "kind": "status",
            "step": 0,
            "message": f"экранов в подсказке: {len(knowledge['screens'])}",
            "url": "",
        }
    )
    names[:] = list(knowledge.get("secretsToRedact") or [])
    if on_secrets:
        on_secrets(names)
    trace.write_knowledge(knowledge)
    return knowledge
