"""LLM v0.0.2 · 永远beta

一个本来只会喊「繁忙」的假模型，现在多了点真东西：
四则运算、单位换算、跨启动记忆，以及一个跑在 CPU 上的 0.5B 小模型。

启动：python main.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time

import webview

from llmforever.brain import Brain
from llmforever.memory import Memory
from llmforever.model import LocalModel

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(ROOT, "index.html")

END_WORDS = ("退出", "再见", "结束对话", "exit", "quit", "bye")


class Session:
    def __init__(self) -> None:
        self.started = time.time()
        self.ended = False
        self.turns = 0
        self.brain = Brain(memory=Memory(), model=LocalModel(), limit=20)

    # ---------------------------------------------------------- 预热

    def warm_up(self) -> None:
        """后台加载模型，免得第一句话等十几秒还以为是卡死了。"""
        def run() -> None:
            try:
                self.brain.model.load()
            except Exception:
                pass

        threading.Thread(target=run, name="warm-up", daemon=True).start()

    # ---------------------------------------------------------- 对话

    def chat(self, prompt: str) -> list:
        text = (prompt or "").strip()
        self.turns += 1

        if text in END_WORDS:
            self.ended = True
            return [
                ("__END__", ""),
                ("meta", "对话已结束。" + self.report()),
            ]

        if self.ended:
            return [("meta", "对话已结束，重启窗口再聊（题外话：重启也还是繁忙）。")]

        out = self.brain.answer(text)
        # 让 UI 的“正在输入”至少亮一下，不然瞬时回答会显得很突兀
        return [("__delay__", "0.35")] + list(out)

    # ---------------------------------------------------------- 报告

    def report(self) -> str:
        stats = self.brain.model.stats()
        data = {
            "version": "0.0.2",
            "turns": self.turns,
            "model_turns": self.brain.used,
            "route": self.brain.last_route,
            "tokens": stats["tokens"],
            "seconds": stats["seconds"],
            "elapsed": round(time.time() - self.started, 1),
        }
        return "本次会话：%d 轮，模型回答 %d 次，%s tok。JSON：%s" % (
            data["turns"],
            data["model_turns"],
            data["tokens"],
            json.dumps(data, ensure_ascii=False),
        )


class Api:
    def __init__(self, session: Session) -> None:
        self.session = session

    def chat(self, prompt: str) -> list:
        return self.session.chat(prompt)

    def quota(self) -> dict:
        return self.session.brain.quota()

    def status(self) -> str:
        return self.session.brain._status_line()


def serve_web(session: "Session", port: int = 0) -> int:
    """浏览器模式：标准库起一个本地服务，免 pywebview。"""
    import json as _json
    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    page = open(INDEX, "rb").read()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # 静音
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send(200, page, "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = _json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                payload = {}
            args = payload.get("args") or []
            try:
                if self.path == "/api/chat":
                    result = session.chat(str(args[0]) if args else "")
                elif self.path == "/api/quota":
                    result = session.brain.quota()
                elif self.path == "/api/status":
                    result = session.brain._status_line()
                else:
                    self._send(404, b"not found", "text/plain; charset=utf-8")
                    return
            except Exception as exc:  # 别让一个异常打死服务
                self._send(500, _json.dumps({"error": str(exc)}).encode(), "application/json")
                return
            body = _json.dumps(result, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    print("浏览器模式已启动：%s" % url)
    print("按 Ctrl+C 退出。")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
        print(session.report())
    return 0


def main() -> int:
    if not os.path.exists(INDEX):
        print("找不到 index.html：%s" % INDEX, file=sys.stderr)
        return 1

    session = Session()
    session.warm_up()

    if "--web" in sys.argv[1:]:
        port = 0
        for i, arg in enumerate(sys.argv[1:]):
            if arg.startswith("--port="):
                port = int(arg.split("=", 1)[1])
        return serve_web(session, port)

    api = Api(session)

    window = webview.create_window(
        "LLM v0.0.2 · 永远beta",
        INDEX,
        js_api=api,
        width=980,
        height=760,
        min_size=(720, 560),
        background_color="#0b0d12",
    )
    webview.start()
    print(session.report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
