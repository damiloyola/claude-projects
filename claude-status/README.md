# claude-status: etapa 1

Monitor local del estado de tus sesiones de Claude Code, alimentado por hooks.
Solo usa Python 3 (librería estándar) y `curl`. Todo corre en `127.0.0.1:8765`.

| Archivo | Para qué |
|---|---|
| `server.py` | Servidor: `POST /event`, `GET /state`, `GET /events`, `GET /` (página) |
| `static/index.html` | Página que se actualiza sola cada 1 s |
| `hook.py` | Script que llama Claude Code. Reenvía solo evento, sesión, proyecto y hora |
| `install_hooks.py` | Agrega o quita los hooks en un `settings.json`: muestra el diff, pide confirmación y hace backup |
| `start.sh` / `stop.sh` | Inician y detienen el servidor en segundo plano |
| `test-events.sh` | Manda eventos falsos de "personal" y "trabajo" |
| `check-managed.sh` | Solo lectura: busca managed settings que bloqueen hooks |
| `events.log` | Log de eventos en formato JSON Lines (se crea solo y rota a los 5 MB) |

## 0. Instalar en la Mac

```sh
python3 --version   # si macOS ofrece instalar las Command Line Tools, aceptá y volvé a probar
mkdir -p ~/Downloads/cs-tmp && cd ~/Downloads/cs-tmp
curl -fL -o cs.tar.gz https://codeload.github.com/damiloyola/claude-projects/tar.gz/refs/heads/claude/claude-code-session-monitor-xp5hm0
tar -xzf cs.tar.gz --strip-components=1
cp -R claude-status ~/claude-status
cd ~/claude-status && ls
```

## 1. Iniciar y detener el servidor

```sh
./start.sh          # en segundo plano; luego abrí http://127.0.0.1:8765
./stop.sh           # lo detiene
python3 server.py   # alternativa: en primer plano, se corta con Ctrl+C
```

## 2. Probar sin Claude Code

```sh
./test-events.sh      # un paso cada 2 s; ./test-events.sh 5 = más lento
```

En la página vas a ver amarillo, luego rojo, verde y por último gris, con tarjetas de las dos cuentas.

## 3. Instalar los hooks (solo cuenta personal)

```sh
python3 install_hooks.py --cuenta personal --dry-run   # solo muestra el diff
python3 install_hooks.py --cuenta personal             # muestra el diff y pregunta [s/N]
```

- Hace merge: agrega un grupo propio en `UserPromptSubmit`, `Stop`, `Notification`,
  `SubagentStop` y `SessionEnd` sin tocar los hooks ni las claves que ya tengas.
- Antes de escribir guarda un backup en `~/.claude/settings.json.bak-AAAAMMDD-HHMMSS`.
- Los hooks llevan `"async": true`, así corren en segundo plano y no demoran a Claude
  Code. El formato sale de https://code.claude.com/docs/en/hooks.
- Si lo corrés de nuevo, no duplica nada. Para quitarlos: `python3 install_hooks.py --cuenta personal --remove`.
- Guarda la ruta absoluta de `hook.py`. Si movés la carpeta, volvé a correrlo.

## 4. Verificar con una sesión real

1. **Reiniciá las sesiones de Claude Code** que tengas abiertas (cerralas y abrilas
   de nuevo). La documentación dice que los cambios en `settings.json` se detectan
   en caliente, pero reiniciar es lo más seguro. Con `/hooks` dentro de Claude Code
   ves qué hooks quedaron cargados.
2. Con el servidor corriendo y la página abierta, mandá un prompt corto ("decí hola").
   La tarjeta se pone **amarilla** y, cuando responde, **verde**.
3. Provocá un pedido de permiso, por ejemplo: "creá el archivo /tmp/prueba.txt con
   el texto hola" (en modo de permisos por defecto). Mientras espera tu aprobación,
   la tarjeta se pone **roja**.
4. Si algo no aparece, mirá `events.log` y `server.out`.

## Estados

| Color | Estado | Evento |
|---|---|---|
| gris | sin datos / sesión cerrada | (ninguno) / `SessionEnd` |
| amarillo | trabajando | `UserPromptSubmit` |
| verde | terminó | `Stop` |
| rojo | necesita algo de vos | `Notification` |

- `SubagentStop` solo actualiza "hace cuánto"; el color no cambia.
- Las notificaciones `idle_prompt`, `auth_success` y `agent_completed` no pasan la
  tarjeta a rojo. `idle_prompt` llega cuando la sesión ya terminó y lleva un rato
  esperando, y pintaría de rojo todo lo que está en verde.
- Limitación conocida: después de aprobar un permiso, la tarjeta sigue en rojo hasta
  el próximo `Stop`. Esto se puede mejorar en la etapa 2 con `PostToolUse`.
- Las sesiones cerradas desaparecen a los 30 min.

## API (para la barra de menú y el ESP32)

`GET /state`:

```json
{"server_time": 1791228650.6, "overall": "attention", "overall_color": "red",
 "counts": {"attention": 1, "working": 0, "done": 2, "ended": 1, "unknown": 0},
 "sessions": [{"account": "personal", "session_id": "…", "project": "mi-blog",
               "status": "done", "color": "green", "last_event": "Stop",
               "last_ts": 1791228650.0, "age_s": 0.7}]}
```

`overall` es el estado más urgente de todos (rojo > amarillo > verde > gris), que es
justo lo que necesita un LED único o un ícono de barra de menú.

`POST /event` exige `Content-Type: application/json` y `Host` igual a
127.0.0.1 o localhost, así una página web cualquiera no puede inyectar eventos.
Para el ESP32 hará falta escuchar en la red local. Para eso existe
`CLAUDE_STATUS_HOST=0.0.0.0`, pero **no lo uses todavía**: se va a cerrar bien en la
etapa del ESP32.

## Cuenta laboral (todavía NO está configurada)

1. Corré `./check-managed.sh` (solo lee). Si encuentra `allowManagedHooksOnly: true`,
   los hooks propios están bloqueados por la organización y no hay que esquivarlo.
2. Abrí Claude Code con la cuenta laboral y corré `/status`. En la línea
   `Setting sources` ves si aplican managed settings del servidor (consola de
   claude.ai), que no aparecen en archivos locales.
3. Cuando confirmes dónde está su carpeta de configuración (por ejemplo
   `CLAUDE_CONFIG_DIR=~/.claude-trabajo`):
   `python3 install_hooks.py --cuenta trabajo --config-dir ~/.claude-trabajo --dry-run`

## Privacidad

`hook.py` lee el JSON de stdin, pero reenvía solo `hook_event_name`, `session_id`,
el nombre de la carpeta del `cwd`, la hora y, en `Notification`, el tipo de
notificación (por ejemplo `permission_prompt`). Nunca reenvía el prompt, el mensaje,
`transcript_path` ni código.
