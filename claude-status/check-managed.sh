#!/bin/sh
# Solo LECTURA: busca managed settings que puedan bloquear hooks propios
# (allowManagedHooksOnly / disableAllHooks). No modifica nada.
DIR="/Library/Application Support/ClaudeCode"
found=0
echo "== Archivos managed en $DIR =="
if [ -d "$DIR" ]; then
  ls -la "$DIR" "$DIR/managed-settings.d" 2>/dev/null
  for f in "$DIR/managed-settings.json" "$DIR"/managed-settings.d/*.json; do
    [ -f "$f" ] || continue
    if grep -E '"(allowManagedHooksOnly|disableAllHooks)"' "$f"; then
      echo "   ^ en $f"; found=1
    fi
  done
else
  echo "(no existe)"
fi

echo
echo "== Perfil MDM (dominio com.anthropic.claudecode) =="
for p in "/Library/Managed Preferences/com.anthropic.claudecode.plist" \
         "/Library/Managed Preferences/$(id -un)/com.anthropic.claudecode.plist"; do
  if [ -f "$p" ]; then
    echo "$p:"
    plutil -p "$p" 2>/dev/null | grep -E 'allowManagedHooksOnly|disableAllHooks' && found=1
  fi
done
[ $found -eq 0 ] && echo "(nada que bloquee hooks en archivos/MDM locales)"

echo
echo "IMPORTANTE: los 'server-managed settings' de la consola de claude.ai (cuenta de"
echo "una organización) no quedan en estos archivos. Para verlos, abrí Claude Code con"
echo "esa cuenta, corré /status y mirá la línea 'Setting sources'; con /hooks ves qué"
echo "hooks están activos de verdad."
