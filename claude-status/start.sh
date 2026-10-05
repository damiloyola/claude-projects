#!/bin/sh
# Inicia el servidor en segundo plano. Uso: ./start.sh   (para verlo en primer plano: python3 server.py)
cd "$(dirname "$0")" || exit 1
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then
  echo "Ya está corriendo (pid $(cat server.pid)): http://127.0.0.1:8765"
  exit 0
fi
nohup python3 server.py > server.out 2>&1 &
echo $! > server.pid
sleep 0.5
if kill -0 "$(cat server.pid)" 2>/dev/null; then
  echo "Servidor iniciado (pid $(cat server.pid)): http://127.0.0.1:8765"
else
  echo "No arrancó. Mirá server.out:"; cat server.out; rm -f server.pid; exit 1
fi
