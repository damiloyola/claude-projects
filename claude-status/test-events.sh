#!/bin/sh
# Manda eventos falsos de dos cuentas para ver cambiar la página (no usa Claude Code).
# Uso: ./test-events.sh [segundos_entre_pasos]   (default 2)
URL="${CLAUDE_STATUS_URL:-http://127.0.0.1:8765/event}"
PAUSA="${1:-2}"

send() { # cuenta evento sesion proyecto [notification_type]
  extra=""
  [ -n "$5" ] && extra=",\"notification_type\":\"$5\""
  body="{\"account\":\"$1\",\"event\":\"$2\",\"session_id\":\"$3\",\"project\":\"$4\",\"timestamp\":$(date +%s)$extra}"
  if curl -s -m 1 -o /dev/null -w '' -H 'Content-Type: application/json' -d "$body" "$URL"; then
    echo "  $1 / $4 -> $2${5:+ ($5)}"
  else
    echo "ERROR: no pude conectar con $URL (¿corriste ./start.sh?)"; exit 1
  fi
}
step() { echo "$1"; sleep "$PAUSA"; }

P1="test-personal-aaaa1111"; P2="test-personal-bbbb2222"; T1="test-trabajo-cccc3333"

echo "== Abrí http://127.0.0.1:8765 y mirá las tarjetas =="
send personal UserPromptSubmit "$P1" mi-blog
send trabajo  UserPromptSubmit "$T1" api-facturacion
step "-> amarillo: personal/mi-blog y trabajo/api-facturacion trabajando"

send personal UserPromptSubmit "$P2" scripts-casa
send personal SubagentStop "$P1" mi-blog
step "-> SubagentStop no cambia el color (mi-blog sigue amarillo)"

send trabajo Notification "$T1" api-facturacion permission_prompt
step "-> rojo: trabajo/api-facturacion pide permiso"

send personal Stop "$P1" mi-blog
step "-> verde: personal/mi-blog terminó"

send personal Notification "$P1" mi-blog idle_prompt
step "-> idle_prompt NO pasa a rojo (mi-blog sigue verde)"

send trabajo UserPromptSubmit "$T1" api-facturacion
step "-> amarillo de nuevo: trabajo/api-facturacion siguió trabajando"

send trabajo  Stop "$T1" api-facturacion
send personal Stop "$P2" scripts-casa
step "-> todo verde"

send personal SessionEnd "$P2" scripts-casa
echo "-> gris: personal/scripts-casa cerró la sesión"
echo "Listo. Las sesiones de prueba se quitan solas en 15 s…"
sleep 15
for sid in "$P1:personal" "$P2:personal" "$T1:trabajo"; do
  curl -s -m 1 -o /dev/null -H 'Content-Type: application/json' \
    -d "{\"account\":\"${sid#*:}\",\"session_id\":\"${sid%%:*}\"}" "${URL%/event}/session/forget"
done
echo "Sesiones de prueba quitadas."
