#!/usr/bin/env python3
"""Acciones del menú de la barra (y útiles desde la terminal).

  ./ctl.py forget  <cuenta> <session_id>   quita la sesión de la lista
  ./ctl.py rename  <cuenta> <session_id>   pide un nombre nuevo en una ventanita
  ./ctl.py clean                           quita todas las que no están trabajando ni esperando
  ./ctl.py sound   on|off|toggle           activa o apaga el sonido
"""

import json
import subprocess
import sys
import urllib.request

BASE = "http://127.0.0.1:8765"


def call(path, data=None):
    req = urllib.request.Request(
        BASE + path,
        data=None if data is None else json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="GET" if data is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=2) as resp:
        return json.load(resp)


def ask_name(current):
    """Ventanita de macOS para escribir el nombre. None si se cancela."""
    script = [
        "-e", "on run argv",
        "-e", 'text returned of (display dialog "Nombre para esta sesión (vacío = nombre de la carpeta):" '
              'default answer (item 1 of argv) with title "Claude Status")',
        "-e", "end run",
    ]
    result = subprocess.run(["/usr/bin/osascript", *script, current],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == "forget" and len(argv) == 3:
        call("/session/forget", {"account": argv[1], "session_id": argv[2]})
    elif cmd == "rename" and len(argv) == 3:
        current = next((s["name"] for s in call("/state")["sessions"]
                        if s["account"] == argv[1] and s["session_id"] == argv[2]), "")
        new_name = ask_name(current)
        if new_name is not None:
            call("/session/rename", {"account": argv[1], "session_id": argv[2], "name": new_name})
    elif cmd == "clean":
        call("/sessions/clean", {})
    elif cmd == "sound" and len(argv) == 2:
        value = {"on": True, "off": False}.get(argv[1])
        if value is None:
            value = not call("/config").get("sound")
        call("/config", {"sound": value})
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
