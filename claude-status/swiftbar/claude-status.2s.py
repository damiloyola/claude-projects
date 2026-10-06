#!/usr/bin/env python3
# <xbar.title>Claude Status</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <xbar.desc>Estado de las sesiones de Claude Code (lee http://127.0.0.1:8765/state)</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
"""Plugin de SwiftBar: un punto de color en la barra de menú.

El "2s" del nombre del archivo es cada cuánto se actualiza (podés renombrarlo a
claude-status.1s.py o .5s.py). Solo lee el servidor local; no cambia nada.
"""

import json
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"
# Carpeta del proyecto: la que contiene esta carpeta swiftbar/; si no, ~/claude-status.
HERE = Path(__file__).resolve().parent.parent
PROJECT_DIR = HERE if (HERE / "server.py").exists() else Path.home() / "claude-status"

COLORS = {"red": "#E5484D", "yellow": "#F5B700", "green": "#30A46C", "gray": "#8B8D98"}
LABEL = {
    "attention": "necesita algo",
    "working": "trabajando",
    "done": "terminó",
    "ended": "sesión cerrada",
    "unknown": "sin datos",
}


def clean(text):
    # "|" separa parámetros en SwiftBar; los saltos de línea cortan el ítem.
    return str(text).replace("|", "¦").replace("\n", " ")


def ago(sec):
    sec = int(max(0, sec))
    if sec < 5:
        return "recién"
    if sec < 60:
        return f"hace {sec} s"
    if sec < 3600:
        return f"hace {sec // 60} min"
    return f"hace {sec // 3600} h {(sec % 3600) // 60} min"


def dot(color):
    return f"sfimage=circle.fill sfcolor={COLORS.get(color, COLORS['gray'])}"


def main():
    try:
        with urllib.request.urlopen(BASE + "/state", timeout=0.8) as resp:
            state = json.load(resp)
    except Exception:
        print(f"| sfimage=circle.dashed sfcolor={COLORS['gray']}")
        print("---")
        print("Servidor apagado | color=gray")
        print(f'Iniciar servidor | bash="{PROJECT_DIR / "start.sh"}" terminal=false refresh=true sfimage=play.fill')
        return

    sessions = state.get("sessions", [])
    counts = state.get("counts", {})
    # Barra de menú: punto del estado más urgente + cuántas necesitan algo o trabajan.
    busy = counts.get("attention", 0) or counts.get("working", 0)
    title = str(busy) if busy else ""
    print(f"{title} | {dot(state.get('overall_color', 'gray'))}")
    print("---")

    if not sessions:
        print("Sin sesiones todavía | color=gray")
    for s in sessions:
        app = s.get("app") or "Claude"
        line = f"{clean(s.get('project', '?'))} — {LABEL.get(s.get('status'), s.get('status'))}"
        print(f'{line} | {dot(s.get("color"))} bash=/usr/bin/open param1=-a param2="{clean(app)}" terminal=false')
        print(f"{clean(s.get('last_event', ''))} · {ago(s.get('age_s', 0))} · {clean(app)} | size=11 color=gray")

    print("---")
    print(f"Abrir monitor web | href={BASE} sfimage=safari")
    print(f'Detener servidor | bash="{PROJECT_DIR / "stop.sh"}" terminal=false refresh=true sfimage=stop.fill')


if __name__ == "__main__":
    main()
