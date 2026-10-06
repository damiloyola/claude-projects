#!/bin/sh
# Baja la última versión desde GitHub, la copia en esta carpeta y reinicia el servidor.
# No toca tus datos: events.log, names.json, config.json ni los hooks de Claude Code.
REPO_TGZ="https://codeload.github.com/damiloyola/claude-projects/tar.gz/refs/heads/claude/claude-code-session-monitor-xp5hm0"
DIR="$(cd "$(dirname "$0")" && pwd)"

# Este mismo archivo se reemplaza al actualizar: corremos desde una copia temporal.
if [ -z "$CLAUDE_STATUS_UPDATING" ]; then
  TMP_SELF="$(mktemp "${TMPDIR:-/tmp}/claude-status-update.XXXXXX")"
  cp "$0" "$TMP_SELF" && chmod +x "$TMP_SELF"
  CLAUDE_STATUS_UPDATING=1 exec "$TMP_SELF" "$DIR"
fi
DIR="${1:-$DIR}"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/claude-status.XXXXXX")"
echo "Bajando la última versión…"
if ! curl -fsSL -o "$WORK/cs.tar.gz" "$REPO_TGZ"; then
  echo "No pude bajar la actualización (¿hay internet?). No se cambió nada."; exit 1
fi
tar -xzf "$WORK/cs.tar.gz" -C "$WORK" --strip-components=1 || { echo "Archivo dañado. No se cambió nada."; exit 1; }
[ -f "$WORK/claude-status/server.py" ] || { echo "La descarga no tiene claude-status/. No se cambió nada."; exit 1; }

"$DIR/stop.sh" >/dev/null 2>&1
cp -R "$WORK/claude-status/." "$DIR/"
# La versión vieja del plugin (que se actualizaba cada 2 s) duplicaría el punto.
rm -f "$DIR/swiftbar/claude-status.2s.py"
rm -rf "$WORK"
echo "Archivos actualizados en $DIR"
"$DIR/start.sh"
echo "Listo. La barra de menú se actualiza sola en unos segundos."
rm -f "$0"  # copia temporal de este script
