#!/usr/bin/env python3
"""Hook de Claude Code -> servidor local claude-status.

Uso (desde settings.json):  python3 /ruta/hook.py --cuenta personal

Lee el JSON que Claude Code manda por stdin y reenvía SOLO:
  account, event, session_id, project (nombre de la carpeta del cwd),
  timestamp y, en Notification, notification_type.
Nunca manda prompts, mensajes, transcript ni código.
Nunca falla: ante cualquier error termina en silencio con exit 0.
"""

import json
import os
import sys
import time
import urllib.request

URL = os.environ.get("CLAUDE_STATUS_URL", "http://127.0.0.1:8765/event")
TIMEOUT_S = 1.0


def main():
    account = "sin-cuenta"
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg in ("--cuenta", "--account") and i + 1 < len(argv):
            account = argv[i + 1]
        elif arg.startswith(("--cuenta=", "--account=")):
            account = arg.split("=", 1)[1]

    data = json.loads(sys.stdin.read() or "{}")
    cwd = data.get("cwd") or ""
    payload = {
        "account": account,
        "event": data.get("hook_event_name", ""),
        "session_id": data.get("session_id", ""),
        "project": os.path.basename(os.path.normpath(cwd)) if cwd else "",
        "timestamp": time.time(),
    }
    if payload["event"] == "Notification" and data.get("notification_type"):
        payload["notification_type"] = data["notification_type"]

    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=TIMEOUT_S).read()


if __name__ == "__main__":
    try:
        main()
    except BaseException:  # servidor caído, JSON raro, lo que sea: silencio
        pass
    sys.exit(0)
