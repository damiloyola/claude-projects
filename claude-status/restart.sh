#!/bin/sh
# Reinicia el servidor (por ejemplo, después de cambiar archivos a mano).
cd "$(dirname "$0")" || exit 1
./stop.sh >/dev/null 2>&1
./start.sh
