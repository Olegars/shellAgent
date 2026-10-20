"""Адаптер OpenAI-совместимого API и Ollama. Ключ не пишется в журнал."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Callable

from shellagent.contract import ACTIONS


class StepTimeout(Exception):
    pass


class Cancelled(Exception):
    pass


def parse_model_json(raw: str) -> dict | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("action") not in ACTIONS:
        return None
    return data


def _default_base(provider: str, base_url: str) -> str:
    if base_url:
        return base_url.rstrip("/")
    if provider == "deepseek":
        return "https://api.deepseek.com/v1"
    if provider == "ollama":
        return "http://127.0.0.1:11434"
    return "https://api.openai.com/v1"


def _endpoint(provider: str, base_url: str) -> str:
    base = _default_base(provider, base_url)
    if provider == "ollama":
        if base.endswith("/api/chat"):
            return base
        return base + "/api/chat"
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _payload(provider: str, model: str, user: str, image: bytes | None) -> dict:
    if provider == "ollama":
        message: dict = {"role": "user", "content": user}
        if image:
            import base64

            message["images"] = [base64.standard_b64encode(image).decode("ascii")]
        return {"model": model, "messages": [_system(), message], "stream": False}
    content: list[dict] | str
    if image:
        import base64

        encoded = base64.standard_b64encode(image).decode("ascii")
        content = [
            {"type": "text", "text": user},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
        ]
    else:
        content = user
    return {
        "model": model,
        "temperature": 0.1,
        "messages": [_system(), {"role": "user", "content": content}],
    }


def _system() -> dict:
    return {
        "role": "system",
        "content": (
            "Ты агент поведенческого тестирования киоска компьютерного клуба, "
            "полноэкранного Qt Quick-приложения. Верни один JSON-объект и ничего больше. "
            "Поля: thought, action. action одно из: click, clickAt, type, press, scroll, "
            "wait, done, blocked. "
            "click: name — видимая подпись элемента. "
            "clickAt: x и y в пикселях скриншота и name — подпись того, куда жмёшь. "
            "Координаты clickAt всегда сопровождай name, иначе шаг нельзя проверить политикой. "
            "type: text и name поля. press: key (Enter, Escape, Tab, Up, Down). "
            "scroll: y. wait: ms. done: summary. blocked: reason. "
            "Один шаг — одно действие. Не выдумывай телефон, PIN, пароль и данные карты. "
            "Не выключай компьютер, не закрывай шелл и не уходи в рабочий стол."
        ),
    }


def _extract_content(provider: str, payload: dict) -> str:
    if provider == "ollama":
        message = payload.get("message") or {}
        return str(message.get("content") or "")
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        return "\n".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    return str(content)


class LlmAdapter:
    def __init__(
        self,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        cancel: threading.Event | None = None,
        timeout: float = 45,
        transport: Callable[..., str] | None = None,
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.cancel = cancel or threading.Event()
        self.timeout = timeout
        self.transport = transport

    def complete(self, user: str, image: bytes | None) -> str:
        if self.provider != "ollama" and not self.api_key:
            raise RuntimeError("нет ключа API")
        body = _payload(self.provider, self.model, user, image)
        if self.transport is not None:
            return self._wait(lambda: self.transport(body))
        return self._wait(lambda: self._http(body))

    def _wait(self, call) -> str:
        box: dict = {}
        finished = threading.Event()

        def work() -> None:
            try:
                box["result"] = call()
            except Exception as exc:
                box["error"] = exc
            finished.set()

        threading.Thread(target=work, daemon=True).start()
        while not finished.wait(0.2):
            if self.cancel.is_set():
                raise Cancelled()
        if self.cancel.is_set():
            raise Cancelled()
        if "error" in box:
            err = box["error"]
            if isinstance(err, (StepTimeout, Cancelled)):
                raise err
            if isinstance(err, TimeoutError):
                raise StepTimeout("таймаут шага") from err
            if isinstance(err, urllib.error.URLError) and isinstance(err.reason, TimeoutError):
                raise StepTimeout("таймаут шага") from err
            raise err
        return str(box.get("result") or "")

    def _http(self, body: dict) -> str:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            _endpoint(self.provider, self.base_url),
            data=data,
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        if self.api_key:
            request.add_header("Authorization", "Bearer " + self.api_key)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            exc.read()
            raise RuntimeError(f"модель ответила HTTP {exc.code}")
        except TimeoutError as exc:
            raise StepTimeout("таймаут шага") from exc
        return _extract_content(self.provider, payload)
