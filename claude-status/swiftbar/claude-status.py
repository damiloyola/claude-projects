#!/usr/bin/env python3
# <xbar.title>Claude Status</xbar.title>
# <xbar.version>v2.0</xbar.version>
# <xbar.desc>Estado de las sesiones de Claude Code (lee http://127.0.0.1:8765/state)</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# <swiftbar.type>streamable</swiftbar.type>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
"""Plugin de SwiftBar: punto de color animado en la barra de menú.

Es "streamable": SwiftBar lo deja corriendo y cada bloque que empieza con "~~~"
reemplaza el menú. Así el punto se puede animar sin lanzar un proceso por cuadro.
Solo lee el servidor local; las acciones del menú las hace ctl.py.
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"
HERE = Path(__file__).resolve().parent.parent
PROJECT_DIR = HERE if (HERE / "server.py").exists() else Path.home() / "claude-status"
CTL = PROJECT_DIR / "ctl.py"

FRAME_S = 0.3          # cada cuánto se redibuja (animación)
POLL_S = 1.0           # cada cuánto se consulta el servidor
JUST_DONE_S = 8        # cuánto parpadea en verde una sesión que recién terminó

# Emojis en vez de íconos coloreados: se ven con color en cualquier versión de SwiftBar.
DOTS = {"red": "🔴", "yellow": "🟡", "green": "🟢", "gray": "⚪️"}
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
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


def fetch_state():
    try:
        with urllib.request.urlopen(BASE + "/state", timeout=0.8) as resp:
            return json.load(resp)
    except Exception:
        return None


def header(state, tick):
    """El punto de la barra. tick cuenta cuadros, para animar."""
    if state is None:
        return "⚫️"
    sessions = state.get("sessions", [])
    counts = state.get("counts", {})
    blink = (tick // 2) % 2 == 0  # cambia cada ~0.6 s
    if counts.get("attention"):
        dot = "🔴" if blink else "⭕️"
        return dot + (str(counts["attention"]) if counts["attention"] > 1 else "")
    if counts.get("working"):
        n = counts["working"]
        return f"🟡{SPINNER[tick % len(SPINNER)]}" + (str(n) if n > 1 else "")
    if any(s["status"] == "done" and s.get("status_age_s", 99) < JUST_DONE_S for s in sessions):
        return "🟢" if blink else "⚪️"
    if counts.get("done"):
        return "🟢"
    return "⚪️"


def render(state, tick):
    out = [header(state, tick), "---"]
    if state is None:
        out.append("Servidor apagado (no responde en 127.0.0.1:8765) | color=gray")
        out.append(f'Iniciar servidor | bash="{PROJECT_DIR / "start.sh"}" terminal=false sfimage=play.fill')
        out += ["---", f'Diagnóstico… | bash="{PROJECT_DIR / "doctor.sh"}" terminal=true sfimage=stethoscope']
        return out

    sessions = state.get("sessions", [])
    if not sessions:
        out.append("Sin sesiones abiertas | color=gray")
    for s in sessions:
        acc, sid = clean(s["account"]), clean(s["session_id"])
        app = clean(s.get("app") or "Claude")
        status = s.get("status")
        dot = DOTS.get(s.get("color"), DOTS["gray"])
        spin = f" {SPINNER[tick % len(SPINNER)]}" if status == "working" else ""
        out.append(f"{dot} {clean(s.get('name') or s.get('project', '?'))} — {LABEL.get(status, status)}{spin}")
        out.append(f"--{clean(s.get('last_event', ''))} · {ago(s.get('age_s', 0))} · carpeta {clean(s.get('project', ''))} | color=gray size=11")
        out.append(f'--Ir a {app} | bash=/usr/bin/open param1=-a param2="{app}" terminal=false sfimage=arrow.up.forward.app')
        out.append(f'--Renombrar… | bash="{CTL}" param1=rename param2="{acc}" param3="{sid}" terminal=false sfimage=pencil')
        out.append(f'--Quitar de la lista | bash="{CTL}" param1=forget param2="{acc}" param3="{sid}" terminal=false sfimage=xmark')

    sound_on = state.get("sound", True)
    out += [
        "---",
        f"Abrir monitor web | href={BASE} sfimage=safari",
        f'Sonido al terminar | bash="{CTL}" param1=sound param2=toggle terminal=false checked={str(sound_on).lower()}',
        f'Limpiar terminadas | bash="{CTL}" param1=clean terminal=false sfimage=trash',
        "---",
        f'Diagnóstico… | bash="{PROJECT_DIR / "doctor.sh"}" terminal=true sfimage=stethoscope',
        f'Ver log de eventos | bash=/usr/bin/open param1=-a param2=Console param3="{PROJECT_DIR / "events.log"}" terminal=false sfimage=doc.text',
        f'Actualizar a la última versión… | bash="{PROJECT_DIR / "update.sh"}" terminal=true sfimage=arrow.down.circle',
        f'Reiniciar servidor | bash="{PROJECT_DIR / "restart.sh"}" terminal=false sfimage=arrow.clockwise',
        f'Detener servidor | bash="{PROJECT_DIR / "stop.sh"}" terminal=false sfimage=stop.fill',
    ]
    return out


def main():
    state, last_poll, last_out, tick = None, 0.0, None, 0
    while True:
        now = time.monotonic()
        if now - last_poll >= POLL_S:
            state, last_poll = fetch_state(), now
        out = "\n".join(render(state, tick))
        if out != last_out:  # solo redibujar si cambió algo
            sys.stdout.write("~~~\n" + out + "\n")
            sys.stdout.flush()
            last_out = out
        tick += 1
        time.sleep(FRAME_S)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
