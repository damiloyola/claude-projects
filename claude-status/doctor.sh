#!/bin/sh
# Diagnóstico de claude-status: revisa cada pieza de la cadena y dice dónde se corta.
# Solo lee; no cambia nada.
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"
CONFIG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
ok()   { printf '  \033[32m✔\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✘\033[0m %s\n' "$1"; }
info() { printf '    %s\n' "$1"; }

echo "1) Python"
if PY=$(command -v python3) && "$PY" --version >/dev/null 2>&1; then ok "$("$PY" --version) en $PY"; else bad "python3 no responde"; fi

echo "2) Servidor"
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then ok "proceso corriendo (pid $(cat server.pid))"; else bad "no hay proceso de start.sh (corré ./start.sh)"; fi
if curl -s -m 1 -o /dev/null http://127.0.0.1:8765/state; then ok "responde en http://127.0.0.1:8765"; else bad "no responde en http://127.0.0.1:8765"; [ -f server.out ] && { info "últimas líneas de server.out:"; tail -5 server.out | sed 's/^/      /'; }; fi

if [ -f swiftbar/claude-status.2s.py ]; then
  bad "quedó el plugin viejo swiftbar/claude-status.2s.py: borralo (duplica el punto)"
fi

echo "3) Hooks en $CONFIG"
if [ -f "$CONFIG" ] && grep -q "claude-status/hook.py" "$CONFIG"; then
  ok "instalados ($(grep -c 'claude-status/hook.py' "$CONFIG") entradas)"
  grep -o '"command": *"[^"]*claude-status/hook.py[^"]*"' "$CONFIG" | head -1 | sed 's/^/    /'
  grep -q "$DIR/hook.py" "$CONFIG" || bad "apuntan a otra carpeta, no a $DIR/hook.py (re-corré install_hooks.py)"
else
  bad "no encontré los hooks (corré: python3 install_hooks.py --cuenta personal)"
fi

echo "4) El hook llega al servidor (evento de prueba)"
before=$(wc -l < events.log 2>/dev/null || echo 0)
printf '{"hook_event_name":"Diagnostico","session_id":"doctor","cwd":"%s"}' "$DIR" | python3 hook.py --cuenta doctor
after=$(wc -l < events.log 2>/dev/null || echo 0)
if [ "$after" -gt "$before" ]; then ok "hook.py → servidor → events.log funciona"; else bad "el evento de prueba no llegó a events.log"; fi

echo "5) Últimos eventos reales (events.log)"
if [ -s events.log ]; then
  grep -v '"doctor"' events.log | tail -8 | python3 -c '
import json, sys, time
for line in sys.stdin:
    try:
        e = json.loads(line)
    except ValueError:
        continue
    t = time.strftime("%H:%M:%S", time.localtime(e.get("timestamp", 0)))
    ev, st, pr, app = (e.get(k, "") for k in ("event", "status", "project", "app"))
    print("    %s  %-17s %-9s %s  (%s)" % (t, ev, st, pr, app))'
else
  bad "events.log vacío: Claude Code todavía no mandó eventos"
  info "reiniciá la sesión de Claude Code y mandá un prompt"
fi

echo "6) Estado actual (/state)"
curl -s -m 1 http://127.0.0.1:8765/state | python3 -c '
import json, sys
s = json.load(sys.stdin)
print("    global:", s["overall"])
for x in s["sessions"]:
    print("    - %s: %s (último: %s, hace %d s)" % (x["project"], x["status"], x.get("last_event"), x["age_s"]))
' 2>/dev/null || bad "no pude leer /state"
echo
echo "Si una sesión aparece como \"unknown\" (sin datos): el servidor la conoció a mitad de"
echo "camino (por ejemplo, después de reiniciarlo). Se corrige sola con el próximo prompt."
