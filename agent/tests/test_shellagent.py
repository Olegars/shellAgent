import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from shellagent.contract import parse_run_payload
from shellagent.hands import Observation
from shellagent.imageutil import encode_png, half
from shellagent.llm import parse_model_json
from shellagent.locator import find_shell_exe
from shellagent.logtail import LogTail
from shellagent.loop import run_loop
from shellagent.policy import rejection_reason
from shellagent.redact import redact_text
from shellagent.scanner import scan_repository
from shellagent.server import AgentServer
from shellagent.trace import Trace
from shellagent.verifier import verify


class ScriptModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, user, image):
        self.calls += 1
        return self.replies.pop(0)


class FakeHands:
    def __init__(self, same_shot=False, alive=True):
        self.same_shot = same_shot
        self.alive = alive
        self.actions = []
        self.closed = False
        self.url = "Клуб SHELL"
        self.scale = 1.0
        self.shots = 0

    def bind_trace(self, trace_dir):
        self.trace_dir = trace_dir

    def start(self):
        return None

    def close(self):
        self.closed = True

    def open(self, target):
        self.actions.append(("open", target))
        return ""

    def snapshot(self, path: Path):
        self.shots += 1
        payload = b"same" if self.same_shot else f"shot-{self.shots}".encode()
        path.write_bytes(payload)
        return Observation(
            url=self.url,
            title=self.url,
            text="экран гостя",
            a11y="",
            scale=1.0,
            image=payload,
            alive=self.alive,
        )

    def perform(self, action):
        self.actions.append(action)
        return ""


def _config(root: Path, **overrides):
    data = dict(
        shell_path=str(root),
        exe_path="",
        task="Проверь экран гостя",
        max_steps=6,
        provider="ollama",
        model="test",
        base_url="",
        api_key="",
        allow_login=False,
        allow_launch=False,
        allow_payments=False,
        fidelity="log-only",
    )
    data.update(overrides)
    from shellagent.contract import RunConfig

    return RunConfig(**data)


class AgentTests(unittest.TestCase):
    def test_png_and_half(self):
        rgba = bytes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16])
        smaller, width, height = half(rgba, 2, 2)
        self.assertEqual((width, height), (1, 1))
        self.assertEqual(smaller, bytes([1, 2, 3, 4]))
        png = encode_png(1, 1, smaller)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_policy_blocks_login_pay_launch_and_power(self):
        locked = {"allowLogin": False, "allowLaunch": False, "allowPayments": False}
        self.assertIn("логин", rejection_reason({"action": "click", "name": "Войти"}, locked))
        self.assertIn("оплата", rejection_reason({"action": "clickAt", "x": 1, "y": 2, "name": "Пополнить"}, locked))
        self.assertIn("запуск", rejection_reason({"action": "click", "name": "Steam"}, locked))
        opened = {"allowLogin": True, "allowLaunch": True, "allowPayments": True}
        self.assertIn("выключение", rejection_reason({"action": "click", "name": "Выключить ПК"}, opened))
        self.assertIn("системные", rejection_reason({"action": "press", "key": "Alt+F4"}, opened))
        self.assertIsNone(rejection_reason({"action": "clickAt", "x": 10, "y": 10, "name": "Меню"}, locked))

    def test_contract_and_redact(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "shellPath": tmp,
                "task": "смотри",
                "llm": {"provider": "ollama", "model": "llava"},
            }
            config = parse_run_payload(payload)
            self.assertEqual(config.max_steps, 25)
            self.assertEqual(config.fidelity, "vision")
            with self.assertRaises(ValueError):
                parse_run_payload({"shellPath": tmp, "task": "", "llm": {"provider": "ollama", "model": "m"}})
        self.assertIn("pin=***", redact_text("pin=1234"))
        self.assertNotIn("sk-secretvalue", redact_text("sk-secretvalue"))

    def test_locator_picks_newest_exe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "build" / "debug"
            newer = root / "build" / "release"
            older.mkdir(parents=True)
            newer.mkdir()
            old_exe = older / "appsector0451.exe"
            new_exe = newer / "appsector0451.exe"
            old_exe.write_bytes(b"old")
            new_exe.write_bytes(b"new")
            import os
            os.utime(old_exe, (1, 1))
            os.utime(new_exe, (2, 2))
            self.assertEqual(Path(find_shell_exe(str(root))).resolve(), new_exe.resolve())
            self.assertEqual(find_shell_exe(str(root), str(old_exe)), str(old_exe))

    def test_log_tail_reads_only_new_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shell.log"
            path.write_text("старое\n", encoding="utf-8")
            tail = LogTail([path])
            with path.open("a", encoding="utf-8") as handle:
                handle.write("новое\n")
            self.assertEqual(tail.read_new(), ["новое"])

    def test_scanner_reads_qml_and_invokable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Main.qml").write_text(
                'Window { objectName: "root"\n title: "Клуб SHELL"\n Button { text: "ВОЙТИ" } }\n',
                encoding="utf-8",
            )
            header = root / "src" / "core"
            header.mkdir(parents=True)
            (header / "networkmanager.h").write_text(
                "Q_INVOKABLE void login(const QString &phone, const QString &pin);\n",
                encoding="utf-8",
            )
            (root / "config.ini").write_text("api_key=secret-value\nclub=demo\n", encoding="utf-8")
            knowledge = scan_repository(root)
            self.assertEqual(knowledge["screens"][0]["file"], "Main.qml")
            self.assertIn("ВОЙТИ", knowledge["screens"][0]["labels"])
            self.assertIn("login", knowledge["invokables"])
            self.assertIn("api_key", knowledge["secretsToRedact"])
            self.assertNotIn("secret-value", json.dumps(knowledge))

    def test_verifier_flags_qml_and_crash(self):
        bugs = verify(["qrc: TypeError: x is not a type"], True, ["open"], "shot.png", "SHELL")
        self.assertEqual(bugs[0]["severity"], "major")
        dead = verify([], False, ["open"], "", "SHELL")
        self.assertEqual(dead[0]["title"], "Шелл завершился во время прогона")

    def test_model_json(self):
        action = parse_model_json('```json\n{"thought":"ок","action":"done","summary":"готово"}\n```')
        self.assertEqual(action["action"], "done")
        self.assertIsNone(parse_model_json('{"action":"open"}'))

    def test_loop_done_policy_stuck_and_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Main.qml").write_text("Window { title: \"SHELL\" }\n", encoding="utf-8")
            trace = Trace(root / "traces", "run1")
            hands = FakeHands()
            events = []
            run_loop(
                _config(root),
                events.append,
                threading.Event(),
                hands,
                trace,
                ScriptModel(['{"action":"done","summary":"экран на месте"}']),
            )
            self.assertTrue(hands.closed)
            self.assertEqual(hands.actions, [("open", str(root))])
            self.assertTrue(any(event["kind"] == "done" for event in events))

            trace = Trace(root / "traces", "run2")
            hands = FakeHands()
            events = []
            run_loop(
                _config(root),
                events.append,
                threading.Event(),
                hands,
                trace,
                ScriptModel(['{"action":"click","name":"Войти"}']),
            )
            self.assertTrue(any(event["message"].startswith("blocked:") for event in events))
            self.assertEqual(hands.actions, [("open", str(root))])

            trace = Trace(root / "traces", "run3")
            hands = FakeHands(same_shot=True)
            events = []
            run_loop(
                _config(root),
                events.append,
                threading.Event(),
                hands,
                trace,
                ScriptModel(['{"action":"wait","ms":0}'] * 5),
            )
            self.assertTrue(any("одинаковый экран" in event["message"] for event in events))

            trace = Trace(root / "traces", "run4")
            hands = FakeHands(alive=False)
            events = []
            run_loop(
                _config(root),
                events.append,
                threading.Event(),
                hands,
                trace,
                ScriptModel(['{"action":"done","summary":"нет"}']),
            )
            self.assertTrue(any(event["kind"] == "bug" for event in events))
            self.assertEqual(trace.bugs[0]["severity"], "blocker")

    def test_server_health_and_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            def runner(config, emit, cancel):
                emit({"kind": "done", "step": 1, "message": "готово", "url": "SHELL"})

            httpd = AgentServer(0, "tok", Path(tmp), runner=runner)
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                bare = urllib.request.Request(f"http://127.0.0.1:{port}/health")
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(bare, timeout=2)
                self.assertEqual(denied.exception.code, 401)

                health = urllib.request.Request(
                    f"http://127.0.0.1:{port}/health",
                    headers={"Authorization": "Bearer tok"},
                )
                with urllib.request.urlopen(health, timeout=2) as response:
                    body = json.loads(response.read().decode())
                self.assertEqual(body["contractVersion"], "1")

                payload = json.dumps(
                    {
                        "shellPath": tmp,
                        "task": "смотри",
                        "llm": {"provider": "ollama", "model": "llava"},
                        "fidelity": "log-only",
                    }
                ).encode()
                start = urllib.request.Request(
                    f"http://127.0.0.1:{port}/runs",
                    data=payload,
                    headers={"Authorization": "Bearer tok", "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(start, timeout=2) as response:
                    started = json.loads(response.read().decode())
                self.assertTrue(started["runId"])

                events = urllib.request.Request(
                    f"http://127.0.0.1:{port}/events",
                    headers={"Authorization": "Bearer tok"},
                )
                with urllib.request.urlopen(events, timeout=3) as response:
                    stream = response.read().decode()
                self.assertIn("готово", stream)
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
