"""Локальный демон. Слушает только 127.0.0.1 и требует одноразовый токен."""

from __future__ import annotations

import inspect
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from shellagent import CONTRACT_VERSION
from shellagent.contract import RunConfig, parse_run_payload
from shellagent.loop import run_loop
from shellagent.redact import redact_text
from shellagent.trace import Trace


class EventBus:
    def __init__(self):
        self.events: list[dict] = []
        self.closed = False
        self._cond = threading.Condition()

    def publish(self, event: dict) -> None:
        with self._cond:
            self.events.append(event)
            self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self.closed = True
            self._cond.notify_all()

    def iter_events(self):
        index = 0
        while True:
            with self._cond:
                while index >= len(self.events) and not self.closed:
                    self._cond.wait(timeout=0.3)
                batch = list(self.events[index:])
                finished = self.closed and index + len(batch) >= len(self.events)
            for event in batch:
                yield event
            index += len(batch)
            if finished:
                return


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.bus: EventBus | None = None
        self.cancel: threading.Event | None = None
        self.run_id = ""


class AgentServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int, token: str, trace_root: Path, runner=run_loop):
        self.token = token
        self.trace_root = trace_root
        self.runner = runner
        self.state = AppState()
        super().__init__(("127.0.0.1", port), AgentHandler)


class AgentHandler(BaseHTTPRequestHandler):
    server: AgentServer

    def log_message(self, fmt: str, *args) -> None:
        return

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if header == f"Bearer {self.server.token}":
            return True
        self._json(401, {"error": "unauthorized"})
        return False

    def _json(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        path = urlparse(self.path).path
        if path == "/health":
            self._json(200, {"ok": True, "contractVersion": CONTRACT_VERSION})
            return
        if path == "/events":
            self._events()
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        path = urlparse(self.path).path
        if path == "/runs":
            self._start_run()
            return
        if path.startswith("/runs/") and path.endswith("/cancel"):
            self._cancel(path)
            return
        self._json(404, {"error": "not found"})

    def _events(self) -> None:
        with self.server.state.lock:
            bus = self.server.state.bus
        if bus is None:
            self._json(409, {"error": "нет активного прогона"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for event in bus.iter_events():
                self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _cancel(self, path: str) -> None:
        run_id = path[len("/runs/") : -len("/cancel")].strip("/")
        with self.server.state.lock:
            if run_id != self.server.state.run_id or self.server.state.cancel is None:
                self._json(404, {"error": "прогон не найден"})
                return
            self.server.state.cancel.set()
        self._json(200, {"ok": True})

    def _start_run(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 1_000_000:
            self._json(413, {"error": "слишком большое тело"})
            return
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
            config = parse_run_payload(payload)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        api_key = self.headers.get("X-Api-Key", "") or ""
        config.api_key = api_key
        with self.server.state.lock:
            if self.server.state.thread is not None and self.server.state.thread.is_alive():
                self._json(409, {"error": "прогон уже идёт"})
                return
            trace = Trace(self.server.trace_root, _new_id())
            config.run_id = trace.run_id
            config.trace_dir = str(trace.dir)
            bus = EventBus()
            cancel = threading.Event()
            self.server.state.bus = bus
            self.server.state.cancel = cancel
            self.server.state.run_id = trace.run_id
            holder = {"names": []}

            def emit(partial: dict) -> None:
                _publish(bus, trace, config, partial, holder["names"])

            def on_secrets(names: list[str]) -> None:
                holder["names"] = list(names)

            def launch() -> None:
                try:
                    parameters = inspect.signature(self.server.runner).parameters
                    if len(parameters) <= 3:
                        self.server.runner(config, emit, cancel)
                    else:
                        self.server.runner(
                            config,
                            emit,
                            cancel,
                            _hands(config),
                            trace,
                            _llm(config, cancel),
                            on_secrets,
                        )
                except Exception as exc:
                    emit(
                        {
                            "kind": "error",
                            "step": 0,
                            "message": redact_text(str(exc), holder["names"], [api_key]),
                        }
                    )
                finally:
                    bus.close()

            thread = threading.Thread(target=launch, daemon=True)
            self.server.state.thread = thread
            thread.start()
        self._json(200, {"runId": config.run_id, "traceDir": config.trace_dir})


def _new_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


def _hands(config: RunConfig):
    from shellagent.hands import ShellHands

    return ShellHands(config.shell_path, config.exe_path)


def _llm(config: RunConfig, cancel: threading.Event):
    from shellagent.llm import LlmAdapter

    return LlmAdapter(
        config.provider,
        config.model,
        config.base_url,
        config.api_key,
        cancel=cancel,
    )


def _publish(bus: EventBus, trace: Trace, config: RunConfig, partial: dict, names: list[str]) -> None:
    values = [config.api_key] if config.api_key else []
    event = {
        "seq": trace.next_seq(),
        "runId": config.run_id,
        "kind": partial.get("kind") or "status",
        "step": int(partial.get("step") or 0),
        "message": redact_text(str(partial.get("message") or ""), names, values),
        "screenshotPath": str(partial.get("screenshotPath") or ""),
        "url": redact_text(str(partial.get("url") or ""), names, values),
    }
    trace.append_event(event)
    bus.publish(event)


def serve(port: int, token: str, trace_root: str, runner=run_loop) -> None:
    root = Path(trace_root)
    root.mkdir(parents=True, exist_ok=True)
    httpd = AgentServer(port, token, root, runner)
    httpd.serve_forever()
