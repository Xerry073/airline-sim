# -*- coding: utf-8 -*-
"""HTTP 层：路由分发、JSON 读写、静态文件。"""

import json
from http.server import BaseHTTPRequestHandler

from meta import build_meta
from paths import WEB
from session import Session

# ============================================================
# HTTP 层
# ============================================================

class Handler(BaseHTTPRequestHandler):
    session: Session = None
    server_version = "AirlineSim/1.0"

    # ---------- 工具 ----------

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else \
            json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, fmt, *args):     # 静默访问日志
        return

    # ---------- 路由 ----------

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/health":
            return self._send(200, {"ok": True, "day": self.session.game.day})
        if path == "/api/meta":
            return self._send(200, build_meta(self.session.game))
        if path == "/api/state":
            return self._send(200, self.session.snapshot())
        if path == "/api/market":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            a = (q.get("from", [""])[0] or "").upper()
            b = (q.get("to", [""])[0] or "").upper()
            return self._send(200, self.session.market(a, b))
        if path == "/api/saves":
            return self._send(200, {"ok": True, "saves": self.session.list_saves()})
        # 静态文件
        return self._static(path)

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_json()
        if path == "/api/command":
            action = body.get("action", "")
            res = self.session.apply(action, body.get("args") or {})
            return self._send(200 if res.get("ok") else 400, res)
        if path == "/api/control":
            res = self.session.control(body.get("paused"), body.get("speed"))
            return self._send(200, res)
        if path == "/api/new_game":
            try:
                res = self.session.new_game(str(body.get("mode") or ""))
                return self._send(200, res)
            except Exception as exc:
                return self._send(400, {"ok": False, "reason": str(exc)})
        if path == "/api/save":
            try:
                res = self.session.save_game(body.get("name"))
                return self._send(200, res)
            except Exception as exc:
                return self._send(400, {"ok": False, "reason": str(exc)})
        if path == "/api/load":
            try:
                res = self.session.load_game(body.get("id"))
                return self._send(200, res)
            except Exception as exc:
                return self._send(400, {"ok": False, "reason": str(exc)})
        if path == "/api/delete_save":
            try:
                res = self.session.delete_save(body.get("id"))
                return self._send(200, res)
            except Exception as exc:
                return self._send(400, {"ok": False, "reason": str(exc)})
        if path == "/api/autosave":
            try:
                return self._send(200, self.session.save_autosave())
            except Exception as exc:
                return self._send(400, {"ok": False, "reason": str(exc)})
        if path == "/api/quit":
            try:
                res = self.session.save_autosave()
                self.session.quit_requested = True
            except Exception as exc:
                return self._send(400, {"ok": False, "reason": str(exc)})
            try:
                self._send(200, res)
            finally:
                # 先让响应完整写回浏览器，再停止服务。
                threading.Timer(0.8, self.server.shutdown).start()
            return
        if path == "/api/restart":
            try:
                res = self.session.save_autosave()
                self.session.restart_requested = True
            except Exception as exc:
                return self._send(400, {"ok": False, "reason": str(exc)})
            try:
                self._send(200, res)
            finally:
                threading.Timer(0.8, self.server.shutdown).start()
            return
        return self._send(404, {"ok": False, "reason": "not found"})

    # ---------- 静态 ----------

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        fp = (WEB / path.lstrip("/")).resolve()
        try:
            fp.relative_to(WEB.resolve())
        except ValueError:
            return self._send(403, {"ok": False, "reason": "forbidden"})
        if not fp.is_file():
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
        }.get(fp.suffix.lower(), "application/octet-stream")
        return self._send(200, fp.read_bytes(), ctype)

