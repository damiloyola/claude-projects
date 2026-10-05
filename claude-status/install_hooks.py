#!/usr/bin/env python3
"""Agrega (o quita) los hooks de claude-status en el settings.json de una cuenta.

  python3 install_hooks.py --cuenta personal                 # muestra diff y pregunta
  python3 install_hooks.py --cuenta personal --dry-run       # solo muestra el diff
  python3 install_hooks.py --cuenta trabajo --config-dir ~/.claude-trabajo
  python3 install_hooks.py --cuenta personal --remove        # quita solo nuestros hooks

- Nunca pisa hooks ni claves existentes: solo agrega un grupo propio por evento.
- Es idempotente: si ya están nuestros hooks, no duplica.
- Antes de escribir: muestra el diff, pide confirmación y hace backup con fecha.
Formato según https://code.claude.com/docs/en/hooks (hooks con "async": true).
"""

import argparse
import difflib
import json
import shlex
import shutil
import sys
import time
from pathlib import Path

EVENTS = ["UserPromptSubmit", "Stop", "Notification", "SubagentStop", "SessionEnd"]
HOOK_SCRIPT = Path(__file__).resolve().parent / "hook.py"
MARKER = "claude-status/hook.py"  # para reconocer nuestros hooks


def is_ours(handler):
    return isinstance(handler, dict) and MARKER in str(handler.get("command", ""))


def build_command(cuenta):
    python = shutil.which("python3") or "/usr/bin/python3"
    return f"{shlex.quote(python)} {shlex.quote(str(HOOK_SCRIPT))} --cuenta {shlex.quote(cuenta)}"


def strip_ours(settings):
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        new_groups = []
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                kept = [h for h in group["hooks"] if not is_ours(h)]
                if not kept and len(kept) != len(group["hooks"]):
                    continue  # el grupo era solo nuestro
                group = dict(group, hooks=kept)
            new_groups.append(group)
        if new_groups:
            hooks[event] = new_groups
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]


def add_ours(settings, cuenta):
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        sys.exit('ERROR: "hooks" en settings.json no es un objeto; no lo toco.')
    handler = {
        "type": "command",
        "command": build_command(cuenta),
        "async": True,   # corre en segundo plano: no demora a Claude Code
        "timeout": 5,
    }
    for event in EVENTS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            sys.exit(f'ERROR: "hooks.{event}" no es una lista; no lo toco.')
        # Sin "matcher": dispara en todas las ocurrencias del evento.
        groups.append({"hooks": [dict(handler)]})


def dump(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cuenta", required=True, help="etiqueta de la cuenta (personal, trabajo, …)")
    ap.add_argument("--config-dir", default="~/.claude",
                    help="carpeta de configuración de esa cuenta (CLAUDE_CONFIG_DIR). Default: ~/.claude")
    ap.add_argument("--dry-run", action="store_true", help="solo mostrar el diff")
    ap.add_argument("--remove", action="store_true", help="quitar nuestros hooks")
    ap.add_argument("--yes", action="store_true", help="no preguntar")
    args = ap.parse_args()

    config_dir = Path(args.config_dir).expanduser()
    path = config_dir / "settings.json"
    if not config_dir.is_dir():
        sys.exit(f"ERROR: no existe {config_dir}")

    original_text = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        settings = json.loads(original_text) if original_text.strip() else {}
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: {path} no es JSON válido ({exc}). No toco nada.")
    if not isinstance(settings, dict):
        sys.exit(f"ERROR: {path} no contiene un objeto JSON. No toco nada.")

    before = dump(settings) if original_text.strip() else ""
    strip_ours(settings)  # así re-instalar no duplica (y cambia la cuenta si hace falta)
    if not args.remove:
        add_ours(settings, args.cuenta)
    after = dump(settings)

    if before == after:
        print(f"Sin cambios en {path}.")
        return

    diff = difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"{path} (actual)", tofile=f"{path} (nuevo)")
    sys.stdout.writelines(diff)
    print()
    if original_text.strip() and before != original_text:
        print("Nota: el diff compara contra el JSON re-formateado (indent 2); "
              "el contenido existente se conserva igual.\n")

    if args.dry_run:
        print("--dry-run: no se escribió nada.")
        return
    if not args.yes:
        answer = input(f"¿Aplicar estos cambios a {path}? [s/N] ").strip().lower()
        if answer not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado. No se tocó nada.")
            return

    if path.exists():
        backup = path.with_name(f"settings.json.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(after, encoding="utf-8")
    tmp.replace(path)
    print(f"Listo: {path} actualizado.")


if __name__ == "__main__":
    main()
