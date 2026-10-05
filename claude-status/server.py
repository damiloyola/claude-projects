#!/usr/bin/env python3
"""Servidor local del monitor de sesiones de Claude Code.

Solo librería estándar. Escucha en 127.0.0.1:8765 por defecto.

  POST /event   recibe un evento del hook (JSON)
  GET  /state   estado actual de cada sesión (JSON, pensado para ESP32 / barra de menú)
  GET  /events  últimos 50 eventos (JSON)
  GET  /        página web que se actualiza sola
"""

import json
import os
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HOST = os.environ.get("CLAUDE_STATUS_HOST", "127.0.0.1")
PORT = int(os.environ.get("CLAUDE_STATUS_PORT", "8765"))
LOG_FILE = BASE_DIR / "events.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # al superar 5 MB se rota a events.log.1
MAX_BODY = 4096
RECENT_MAX = 50
ENDED_TTL = 30 * 60  # las sesiones terminadas desaparecen a los 30 min

# Evento de hook -> estado. Los que no están acá no cambian el estado.
EVENT_STATUS = {
    "UserPromptSubmit": "working",
    "Stop": "done",
    "Notification": "attention",
    "SessionEnd": "ended",
}
# Notificaciones que NO significan "te necesito ahora". idle_prompt llega cuando
# Claude ya terminó y la sesión lleva un rato quieta: no la pasamos a rojo.
PASSIVE_NOTIFICATIONS = {"idle_prompt", "auth_success", "agent_completed"}

# Prioridad para el resumen global (para un único LED / ícono de barra de menú).
STATUS_PRIORITY = {"attention": 4, "working": 3, "done": 2, "ended": 1, "unknown": 0}
STATUS_COLOR = {
    "attention": "red",
    "working": "yellow",
    "done": "green",
    "ended": "gray",
    "unknown": "gray",
}
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

lock = threading.Lock()
sessions = {}  # (account, session_id) -> dict
recent = deque(maxlen=RECENT_MAX)


def clean_str(value, limit=200):
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ")[:limit]


def parse_ts(value):
    now = time.time()
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return now
    if ts > 1e12:  # milisegundos
        ts /= 1000
    # Hook y servidor corren en la misma Mac: si la hora es absurda, usamos la nuestra.
    return ts if abs(now - ts) < 86400 else now


def append_log(record):
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            LOG_FILE.replace(LOG_FILE.with_suffix(".log.1"))
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"no pude escribir {LOG_FILE}: {exc}", file=sys.stderr)


def apply_event(data):
    now = time.time()
    record = {
        "account": clean_str(data.get("account"), 40) or "sin-cuenta",
        "event": clean_str(data.get("event"), 40),
        "session_id": clean_str(data.get("session_id"), 80) or "sin-sesion",
        "project": clean_str(data.get("project"), 120) or "?",
        "timestamp": parse_ts(data.get("timestamp")),
        "received": now,
    }
    ntype = clean_str(data.get("notification_type"), 40)
    if ntype:
        record["notification_type"] = ntype

    new_status = EVENT_STATUS.get(record["event"])
    if record["event"] == "Notification" and ntype in PASSIVE_NOTIFICATIONS:
        new_status = None

    key = (record["account"], record["session_id"])
    with lock:
        sess = sessions.get(key)
        if sess is None:
            sess = sessions[key] = {
                "account": record["account"],
                "session_id": record["session_id"],
                "project": record["project"],
                "status": "unknown",
                "first_seen": now,
            }
        sess["project"] = record["project"]
        sess["last_event"] = record["event"]
        sess["last_ts"] = record["timestamp"]
        if new_status:
            sess["status"] = new_status
        record["status"] = sess["status"]
        recent.appendleft(record)
        append_log(record)
    return record


def prune(now):
    for key in [k for k, s in sessions.items()
                if s["status"] == "ended" and now - s.get("last_ts", now) > ENDED_TTL]:
        del sessions[key]


def build_state():
    now = time.time()
    with lock:
        prune(now)
        items = []
        for s in sessions.values():
            item = dict(s)
            item["color"] = STATUS_COLOR.get(s["status"], "gray")
            item["age_s"] = round(max(0.0, now - s.get("last_ts", now)), 1)
            items.append(item)
    items.sort(key=lambda s: (-STATUS_PRIORITY.get(s["status"], 0), s["age_s"]))
    counts = {k: 0 for k in STATUS_PRIORITY}
    for s in items:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    overall = items[0]["status"] if items else "unknown"
    return {
        "server_time": now,
        "overall": overall,
        "overall_color": STATUS_COLOR.get(overall, "gray"),
        "counts": counts,
        "sessions": items,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "claude-status/1"

    def log_message(self, fmt, *args):  # silencio en consola
        pass

    def _host_ok(self):
        # Defensa contra DNS rebinding: si escuchamos solo en loopback,
        # aceptamos únicamente Host 127.0.0.1 / localhost.
        if HOST not in ("127.0.0.1", "localhost"):
            return True
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "host no permitido"})
        path = self.path.split("?", 1)[0]
        if path == "/state":
            return self._send(200, build_state())
        if path == "/events":
            with lock:
                return self._send(200, list(recent))
        if path in ("/", "/index.html"):
            try:
                html = (BASE_DIR / "static" / "index.html").read_bytes()
            except OSError:
                return self._send(500, {"error": "falta static/index.html"})
            return self._send(200, html, "text/html; charset=utf-8")
        return self._send(404, {"error": "no encontrado"})

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, {"error": "host no permitido"})
        if self.path.split("?", 1)[0] != "/event":
            return self._send(404, {"error": "no encontrado"})
        # Exigir application/json obliga a los navegadores a hacer preflight CORS,
        # que no respondemos: una página web cualquiera no puede inyectar eventos.
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._send(415, {"error": "se espera application/json"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            return self._send(413, {"error": "cuerpo vacío o demasiado grande"})
        try:
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return self._send(400, {"error": "JSON inválido"})
        record = apply_event(data)
        return self._send(200, {"ok": True, "status": record["status"]})


def main():
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    print(f"claude-status escuchando en http://{HOST}:{PORT}  (Ctrl+C para salir)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
