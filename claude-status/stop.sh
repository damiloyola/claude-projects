#!/bin/sh
# Detiene el servidor iniciado con start.sh.
cd "$(dirname "$0")" || exit 1
if [ -f server.pid ] && kill "$(cat server.pid)" 2>/dev/null; then
  echo "Servidor detenido."
else
  echo "No había servidor corriendo (según server.pid)."
fi
rm -f server.pid
