#!/usr/bin/env python3
"""Servidor local del monitor de sesiones de Claude Code.

Solo librería estándar. Escucha en 127.0.0.1:8765 por defecto.

  POST /event            recibe un evento del hook (JSON)
  GET  /state            estado actual de cada sesión (JSON, para ESP32 / barra de menú)
  GET  /events           últimos 50 eventos (JSON)
  GET  /                 página web que se actualiza sola
  POST /session/forget   {"account", "session_id"}: quita una sesión de la lista
  POST /session/rename   {"account", "session_id", "name"}: nombre propio ("" = volver al proyecto)
  POST /sessions/clean   quita todas las sesiones que no están trabajando ni esperando
  GET|POST /config       {"sound": true|false}
"""

import json
import os
import subprocess
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
NAMES_FILE = BASE_DIR / "names.json"
CONFIG_FILE = BASE_DIR / "config.json"
# Una sesión desaparece sola si no tiene eventos durante este tiempo, según su estado.
# Claude Code no avisa cuando cerrás una ventana sin /exit, por eso el vencimiento.
STATUS_TTL = {
    "ended": 2 * 60,            # cerrada: se ve 2 min en gris y se va
    "unknown": 2 * 3600,
    "done": 4 * 3600,           # terminó y nadie la volvió a usar en 4 h
    "working": 12 * 3600,       # por si una sesión se cortó a mitad de camino
    "attention": 12 * 3600,
}
DEFAULT_CONFIG = {
    "sound": True,
    "sound_done": "/System/Library/Sounds/Glass.aiff",
    "sound_attention": "/System/Library/Sounds/Ping.aiff",
}
REPLAY_MAX_AGE = 12 * 3600  # al arrancar, se recupera el estado de las últimas 12 h

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
seq = 0  # sube con cada cambio de estado: los clientes detectan cambios sin perderse ninguno


def load_json(path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default
    except (OSError, ValueError):
        return default


def save_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


names = load_json(NAMES_FILE, {})  # "cuenta|session_id" -> nombre propio
config = dict(DEFAULT_CONFIG, **load_json(CONFIG_FILE, {}))


def name_key(account, session_id):
    return f"{account}|{session_id}"


def play_sound(status):
    """Sonido de macOS al terminar o al pedir algo. En segundo plano; nunca falla."""
    path = config.get("sound_done" if status == "done" else "sound_attention", "")
    if not config.get("sound") or sys.platform != "darwin" or not os.path.exists(path):
        return
    try:
        subprocess.Popen(["/usr/bin/afplay", path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def clean_str(value, limit=200):
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ")[:limit]


def parse_ts(value, now=None):
    now = now or time.time()
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


def apply_event(data, replay=False):
    now = time.time()
    if replay:  # al recuperar del log, la "hora actual" es la del evento original
        now = parse_ts(data.get("received"), now)
    record = {
        "account": clean_str(data.get("account"), 40) or "sin-cuenta",
        "event": clean_str(data.get("event"), 40),
        "session_id": clean_str(data.get("session_id"), 80) or "sin-sesion",
        "project": clean_str(data.get("project"), 120) or "?",
        "timestamp": parse_ts(data.get("timestamp"), now),
        "received": now,
        "app": clean_str(data.get("app"), 40),
    }
    ntype = clean_str(data.get("notification_type"), 40) if record["event"] == "Notification" else ""
    if ntype:
        record["notification_type"] = ntype

    if record["event"] == "_forget":  # quitada a mano: se registra para que no vuelva al reiniciar
        with lock:
            sessions.pop((record["account"], record["session_id"]), None)
            if not replay:
                append_log(record)
        return record

    if record["event"] == "Diagnostico":  # evento de prueba de doctor.sh: solo al log
        record["status"] = "ok"
        if not replay:
            with lock:
                append_log(record)
        return record

    new_status = EVENT_STATUS.get(record["event"])
    if record["event"] == "Notification" and ntype in PASSIVE_NOTIFICATIONS:
        new_status = None

    global seq
    key = (record["account"], record["session_id"])
    sound = None
    with lock:
        sess = sessions.get(key)
        if sess is None:
            sess = sessions[key] = {
                "account": record["account"],
                "session_id": record["session_id"],
                "project": record["project"],
                "status": "unknown",
                "first_seen": now,
                "status_since": now,
            }
        sess["project"] = record["project"]
        if record["app"]:
            sess["app"] = record["app"]
        sess["last_event"] = record["event"]
        sess["last_ts"] = record["timestamp"]
        previous = sess["status"]
        if new_status:
            sess["status"] = new_status
        elif sess["status"] == "unknown" and record["event"] == "SubagentStop":
            # Una sesión que ya estaba en marcha antes de que el servidor la viera:
            # si termina un subagente, el agente principal está trabajando.
            sess["status"] = "working"
        if sess["status"] != previous:
            seq += 1
            sess["status_since"] = record["timestamp"]
            if not replay and sess["status"] in ("done", "attention"):
                sound = sess["status"]
        record["status"] = sess["status"]
        recent.appendleft(record)
        if not replay:
            append_log(record)
    if sound:
        play_sound(sound)
    return record


def forget(account, session_id):
    apply_event({"event": "_forget", "account": account, "session_id": session_id})


def prune(now):
    for key in [k for k, s in sessions.items()
                if now - s.get("last_ts", now) > STATUS_TTL.get(s["status"], 3600)]:
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
            item["status_age_s"] = round(max(0.0, now - s.get("status_since", now)), 1)
            item["name"] = names.get(name_key(s["account"], s["session_id"])) or s["project"]
            items.append(item)
    items.sort(key=lambda s: (-STATUS_PRIORITY.get(s["status"], 0), s["age_s"]))
    counts = {k: 0 for k in STATUS_PRIORITY}
    for s in items:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    overall = items[0]["status"] if items else "unknown"
    return {
        "server_time": now,
        "seq": seq,
        "sound": bool(config.get("sound")),
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
        if path == "/config":
            return self._send(200, config)
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
        path = self.path.split("?", 1)[0]
        if path not in ("/event", "/session/forget", "/session/rename", "/sessions/clean", "/config"):
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
        if path == "/event":
            if str(data.get("event", "")).startswith("_"):
                return self._send(400, {"error": "evento reservado"})
            record = apply_event(data)
            return self._send(200, {"ok": True, "status": record["status"]})
        account = clean_str(data.get("account"), 40)
        session_id = clean_str(data.get("session_id"), 80)
        if path == "/session/forget":
            forget(account, session_id)
        elif path == "/session/rename":
            new_name = clean_str(data.get("name"), 60).strip()
            with lock:
                if new_name:
                    names[name_key(account, session_id)] = new_name
                else:
                    names.pop(name_key(account, session_id), None)
                save_json(NAMES_FILE, names)
        elif path == "/sessions/clean":
            with lock:
                idle = [k for k, s in sessions.items() if s["status"] not in ("working", "attention")]
            for acc, sid in idle:
                forget(acc, sid)
        elif path == "/config":
            with lock:
                if "sound" in data:
                    config["sound"] = bool(data["sound"])
                save_json(CONFIG_FILE, config)
        return self._send(200, {"ok": True})


def replay_log():
    """Recupera el estado de las últimas horas desde events.log (para reinicios)."""
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()[-2000:]
    except OSError:
        return 0
    cutoff = time.time() - REPLAY_MAX_AGE
    count = 0
    for line in lines:
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict) and float(data.get("received") or 0) >= cutoff:
            apply_event(data, replay=True)
            count += 1
    return count


def main():
    restored = replay_log()
    if restored:
        print(f"recuperados {restored} eventos de {LOG_FILE.name}")
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
