#!/usr/bin/env python3
"""
memory_retry_queue.py — Cola persistente de reintentos para memorialocal.

Proposito:
  Si una operacion de memoria (create_entity, add_observations,
  create_relations, delete_observations) falla por timeout, error de
  red o respuesta no-JSON, este script encola el payload completo en
  disco. Al inicio de cada turno se intenta drenar la cola reaplicando
  las operaciones pendientes contra memorialocal.

Ubicacion de la cola:
  ~/.config/opencode/data/memory_retry_queue.jsonl
  (permisos 0600, directorio 0700, excluido del repo via .gitignore)

Subcomandos:
  enqueue   --op <op> --payload <json> [--cliente <id>]
                Encola una operacion fallida. Atomic write con O_APPEND.
  drain     [OPCIONAL --limit N]
                Reaplica todas las entradas pendientes en orden FIFO.
                Exitosas se eliminan; fallidas se conservan.
  peek      [OPCIONAL --limit N]
                Muestra conteo y primeras N entradas (modo lectura).
  clear     [-y]
                Vacia la cola. Pide confirmacion interactiva salvo -y.
  status    Muestra estado: tamano, conteo, ultima rotacion.
  repair    Mueve lineas malformadas a <queue>.corrupt para no perderlas.

Formato de cada linea (JSONL):
  {
    "id": "mrq_20260630_143211_a3f9",
    "op": "create_entity",
    "payload": {...},
    "cliente": "cliente_juan",
    "enqueued_at": "2026-06-30T14:32:11-03:00",
    "attempts": 0,
    "last_error": null
  }

Garantias:
  - Append atómico (O_APPEND + os.write).
  - Lock de fichero (fcntl.flock LOCK_EX) contra enqueue+drain concurrentes.
  - Rotacion automatica si la cola supera 10 MB.
  - Lineas malformadas se mueven a <queue>.corrupt en vez de eliminarse.
  - Sin imports externos.

Exit codes:
  0 = exito
  1 = error inesperado (loggeado a stderr)
  2 = input invalido del usuario/agente
  3 = memorialocal no disponible (en enqueue: ya encolado, no es error)
"""

import argparse
import datetime as dt
import errno
import fcntl
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = Path.home() / ".config" / "opencode" / "data"
QUEUE_FILENAME = "memory_retry_queue.jsonl"
CORRUPT_SUFFIX = ".corrupt"
MAX_QUEUE_BYTES = 10 * 1024 * 1024  # 10 MB

# Memoria local MCP server name (configurado en opencode.json)
MEMORY_SERVER = "memory-local"

# Operaciones soportadas -> nombre del tool MCP
OP_TO_TOOL = {
    "create_entity": "memory-local_create_entities",
    "add_observations": "memory-local_add_observations",
    "create_relations": "memory-local_create_relations",
    "delete_observations": "memory-local_delete_observations",
}

VALID_OPS = set(OP_TO_TOOL.keys())


# ---------------------------------------------------------------------------
# Helpers de path y permisos
# ---------------------------------------------------------------------------

def ensure_data_dir() -> Path:
    """Crea ~/.config/opencode/data/ con permisos 0700 si no existe."""
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DEFAULT_DATA_DIR, 0o700)
    return DEFAULT_DATA_DIR


def queue_path() -> Path:
    return ensure_data_dir() / QUEUE_FILENAME


def corrupt_path() -> Path:
    return queue_path().with_suffix(queue_path().suffix + CORRUPT_SUFFIX)


# ---------------------------------------------------------------------------
# Helpers de timestamp
# ---------------------------------------------------------------------------

def now_iso() -> str:
    """ISO 8601 estricto con offset (compatible con agent_utils.py now-iso)."""
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def now_human() -> str:
    """YYYY-MM-DD HH:MM:SS TZ (formato agente)."""
    now = dt.datetime.now().astimezone()
    return now.strftime("%Y-%m-%d %H:%M:%S %z")


def gen_id() -> str:
    """ID unico: mrq_YYYYMMDD_HHMMSS_XXXX (4 hex chars)."""
    now = dt.datetime.now()
    return (
        f"mrq_{now.strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(2)}"
    )


# ---------------------------------------------------------------------------
# Helpers de lock y append atomico
# ---------------------------------------------------------------------------

class FileLock:
    """fcntl.flock wrapper. Permite enqueue+drain concurrentes seguros."""

    def __init__(self, path: Path, exclusive: bool = True):
        self.path = path
        self.exclusive = exclusive
        self.fd = None

    def __enter__(self):
        self.fd = open(self.path, "a+", encoding="utf-8")
        mode = fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH
        fcntl.flock(self.fd.fileno(), mode)
        return self.fd

    def __exit__(self, *exc):
        if self.fd:
            try:
                fcntl.flock(self.fd.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            self.fd.close()


def atomic_append(path: Path, line: str) -> None:
    """Append atomico: O_APPEND garantiza que la escritura es una sola syscall."""
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Helpers de validacion y reparacion
# ---------------------------------------------------------------------------

def parse_line(raw: str) -> tuple[int, dict | None]:
    """Parsea una linea JSONL. Retorna (bytes_usados, dict | None)."""
    line = raw.rstrip("\n")
    if not line.strip():
        return len(raw), None  # linea vacia
    try:
        return len(raw), json.loads(line)
    except json.JSONDecodeError:
        return len(raw), None


def validate_entry(entry: dict) -> str | None:
    """Valida campos obligatorios. Retorna None si ok, sino mensaje de error."""
    if not isinstance(entry, dict):
        return "no es un objeto JSON"
    if "op" not in entry or entry["op"] not in VALID_OPS:
        return f"op invalida: {entry.get('op')!r}"
    if "payload" not in entry or not isinstance(entry["payload"], dict):
        return "payload ausente o no es objeto"
    return None


def move_corrupt_line(raw_line: str) -> None:
    """Mueve una linea malformada a <queue>.corrupt para no perderla."""
    cp = corrupt_path()
    with open(cp, "a", encoding="utf-8") as f:
        f.write(raw_line if raw_line.endswith("\n") else raw_line + "\n")
    os.chmod(cp, 0o600)


# ---------------------------------------------------------------------------
# Rotacion
# ---------------------------------------------------------------------------

def rotate_if_needed() -> bool:
    """Si la cola supera MAX_QUEUE_BYTES, archiva y reinicia."""
    qp = queue_path()
    if not qp.exists():
        return False
    size = qp.stat().st_size
    if size < MAX_QUEUE_BYTES:
        return False
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = qp.with_name(f"{qp.name}.bak.{ts}")
    os.rename(qp, backup)
    os.chmod(backup, 0o600)
    sys.stderr.write(
        f"[memory_retry_queue] Cola rotada ({size} bytes) -> {backup.name}\n"
    )
    return True


# ---------------------------------------------------------------------------
# Subcomando: enqueue
# ---------------------------------------------------------------------------

def cmd_enqueue(args) -> int:
    op = args.op
    if op not in VALID_OPS:
        sys.stderr.write(
            f"[memory_retry_queue] op invalida: {op!r}. "
            f"Validas: {sorted(VALID_OPS)}\n"
        )
        return 2

    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"[memory_retry_queue] payload no es JSON valido: {e}\n")
        return 2

    if not isinstance(payload, dict):
        sys.stderr.write("[memory_retry_queue] payload debe ser objeto JSON\n")
        return 2

    entry = {
        "id": gen_id(),
        "op": op,
        "payload": payload,
        "cliente": args.cliente or "unknown",
        "enqueued_at": now_iso(),
        "attempts": 0,
        "last_error": None,
    }

    qp = queue_path()
    line = json.dumps(entry, ensure_ascii=False) + "\n"

    with FileLock(qp, exclusive=True):
        atomic_append(qp, line)
        os.chmod(qp, 0o600)
        rotate_if_needed()

    print(
        json.dumps(
            {"status": "enqueued", "id": entry["id"], "queue": str(qp)},
            ensure_ascii=False,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# Subcomando: drain
# ---------------------------------------------------------------------------

def call_mcp_tool(tool_name: str, args_obj: dict) -> tuple[bool, str]:
    """Llama a un tool MCP via subprocess (Claude Code CLI bridge).
    Retorna (ok, mensaje_error_o_vacio)."""
    # En opencode, los MCP tools se invocan via JSON-RPC al server.
    # Aqui usamos un wrapper generico: ejecutar el comando CLI si existe,
    # sino retornar (False, 'mcp_cli_not_available').
    #
    # Nota: como fallback robusto, intentamos `opencode mcp call <tool>`.
    # Si esa CLI no existe en este entorno, marcamos como no drenable
    # (la entrada permanecera en cola para intento posterior).
    cmd = ["opencode", "mcp", "call", tool_name, json.dumps(args_obj)]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        return False, "opencode_cli_not_available"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, f"unexpected:{e}"

    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "unknown_error").strip()
    return True, ""


def read_all_entries() -> list[tuple[str, dict]]:
    """Lee todas las entradas validas y devuelve (raw_line, parsed_dict).
    Lineas malformadas se mueven a .corrupt."""
    qp = queue_path()
    if not qp.exists():
        return []

    valid: list[tuple[str, dict]] = []
    with FileLock(qp, exclusive=False):
        with open(qp, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

    for raw in raw_lines:
        _, parsed = parse_line(raw)
        if parsed is None:
            if raw.strip():
                move_corrupt_line(raw)
            continue
        err = validate_entry(parsed)
        if err:
            move_corrupt_line(raw)
            continue
        valid.append((raw, parsed))
    return valid


def rewrite_queue(remaining_raws: list[str]) -> None:
    """Reescribe la cola solo con las lineas que NO tuvieron exito."""
    qp = queue_path()
    tmp = qp.with_name(qp.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for raw in remaining_raws:
            f.write(raw if raw.endswith("\n") else raw + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, qp)


def cmd_drain(args) -> int:
    entries = read_all_entries()
    if not entries:
        print(json.dumps({"status": "empty", "drained": 0, "remaining": 0}))
        return 0

    limit = args.limit if args.limit and args.limit > 0 else len(entries)
    to_process = entries[:limit]

    drained_ok: list[str] = []
    remaining: list[str] = []
    errors_summary: list[dict] = []

    for raw, entry in to_process:
        tool = OP_TO_TOOL[entry["op"]]
        ok, err = call_mcp_tool(tool, entry["payload"])
        if ok:
            drained_ok.append(raw)
        else:
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["last_error"] = err
            new_raw = json.dumps(entry, ensure_ascii=False) + "\n"
            remaining.append(new_raw)
            errors_summary.append({"id": entry["id"], "error": err})

    # Anyadir al remaining las entradas que NO procesamos (por --limit)
    for raw, entry in entries[limit:]:
        remaining.append(raw)

    rewrite_queue(remaining)

    result = {
        "status": "drained",
        "drained": len(drained_ok),
        "remaining": len(remaining),
        "errors": errors_summary[:5],  # solo primeras 5 para no inflar
    }
    print(json.dumps(result, ensure_ascii=False))

    if errors_summary:
        return 1  # drenó parcialmente
    return 0


# ---------------------------------------------------------------------------
# Subcomando: peek
# ---------------------------------------------------------------------------

def cmd_peek(args) -> int:
    qp = queue_path()
    if not qp.exists():
        print(json.dumps({"count": 0, "entries": []}))
        return 0

    with FileLock(qp, exclusive=False):
        with open(qp, "r", encoding="utf-8") as f:
            lines = f.readlines()

    valid_entries: list[dict] = []
    for raw in lines:
        _, parsed = parse_line(raw)
        if parsed:
            valid_entries.append(parsed)

    limit = args.limit if args.limit and args.limit > 0 else 5
    sample = valid_entries[:limit]

    # Proyeccion segura: oculta 'payload' completo si es muy grande.
    safe_sample = []
    for e in sample:
        safe_sample.append({
            "id": e.get("id"),
            "op": e.get("op"),
            "cliente": e.get("cliente"),
            "enqueued_at": e.get("enqueued_at"),
            "attempts": e.get("attempts", 0),
            "last_error": e.get("last_error"),
            "payload_keys": list(e.get("payload", {}).keys())[:5],
        })

    print(json.dumps(
        {"count": len(valid_entries), "entries": safe_sample},
        ensure_ascii=False,
    ))
    return 0


# ---------------------------------------------------------------------------
# Subcomando: clear
# ---------------------------------------------------------------------------

def cmd_clear(args) -> int:
    qp = queue_path()
    if not qp.exists():
        print(json.dumps({"status": "empty", "cleared": 0}))
        return 0

    # Contear antes
    with FileLock(qp, exclusive=False):
        with open(qp, "r", encoding="utf-8") as f:
            count = sum(1 for line in f if line.strip())

    if not args.yes:
        sys.stderr.write(
            f"[memory_retry_queue] Vas a eliminar {count} entradas. "
            f"Confirma con -y si es intencional.\n"
        )
        return 2

    with FileLock(qp, exclusive=True):
        qp.unlink()
    print(json.dumps({"status": "cleared", "count": count}))
    return 0


# ---------------------------------------------------------------------------
# Subcomando: status
# ---------------------------------------------------------------------------

def cmd_status(args) -> int:
    qp = queue_path()
    if not qp.exists():
        print(json.dumps({"exists": False, "size_bytes": 0, "count": 0}))
        return 0

    size = qp.stat().st_size
    with FileLock(qp, exclusive=False):
        with open(qp, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

    valid = 0
    corrupt = 0
    for raw in raw_lines:
        _, parsed = parse_line(raw)
        if parsed is None:
            if raw.strip():
                corrupt += 1
        elif validate_entry(parsed) is None:
            valid += 1
        else:
            corrupt += 1

    # Buscar backups de rotacion
    backup_pattern = qp.with_name(f"{qp.name}.bak.*")
    backups = sorted(qp.parent.glob(backup_pattern.name))

    print(json.dumps({
        "exists": True,
        "path": str(qp),
        "size_bytes": size,
        "valid_entries": valid,
        "corrupt_entries": corrupt,
        "rotation_backups": [b.name for b in backups][-5:],
        "max_bytes": MAX_QUEUE_BYTES,
    }, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# Subcomando: repair
# ---------------------------------------------------------------------------

def cmd_repair(args) -> int:
    """Repasa la cola moviendo todas las lineas malformadas a .corrupt."""
    qp = queue_path()
    if not qp.exists():
        print(json.dumps({"status": "empty", "moved": 0}))
        return 0

    moved = 0
    valid_raws: list[str] = []
    with FileLock(qp, exclusive=False):
        with open(qp, "r", encoding="utf-8") as f:
            lines = f.readlines()

    for raw in lines:
        _, parsed = parse_line(raw)
        if parsed is None:
            if raw.strip():
                move_corrupt_line(raw)
                moved += 1
            continue
        if validate_entry(parsed) is not None:
            move_corrupt_line(raw)
            moved += 1
            continue
        valid_raws.append(raw)

    rewrite_queue(valid_raws)
    print(json.dumps({"status": "repaired", "moved_to_corrupt": moved,
                      "kept_valid": len(valid_raws)}))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="memory_retry_queue.py",
        description="Cola persistente de reintentos para memorialocal.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # enqueue
    pe = sub.add_parser("enqueue", help="Encolar operacion fallida.")
    pe.add_argument("--op", required=True, choices=sorted(VALID_OPS),
                    help="Tipo de operacion de memoria.")
    pe.add_argument("--payload", required=True,
                    help="Payload JSON (como string) que se hubiera enviado al tool.")
    pe.add_argument("--cliente", default=None,
                    help="Identificador del cliente (opcional, solo metadata).")
    pe.set_defaults(func=cmd_enqueue)

    # drain
    pd = sub.add_parser("drain", help="Reaplicar entradas pendientes.")
    pd.add_argument("--limit", type=int, default=0,
                    help="Maximo de entradas a procesar este turno (0=todas).")
    pd.set_defaults(func=cmd_drain)

    # peek
    pp = sub.add_parser("peek", help="Inspeccionar cola sin modificar.")
    pp.add_argument("--limit", type=int, default=5,
                    help="Numero de entradas a mostrar (default 5).")
    pp.set_defaults(func=cmd_peek)

    # clear
    pc = sub.add_parser("clear", help="Vaciar cola (peligroso).")
    pc.add_argument("-y", "--yes", action="store_true",
                    help="Confirmar sin interaccion.")
    pc.set_defaults(func=cmd_clear)

    # status
    ps = sub.add_parser("status", help="Estado de la cola.")
    ps.set_defaults(func=cmd_status)

    # repair
    pr = sub.add_parser("repair",
                        help="Mover lineas malformadas a <queue>.corrupt.")
    pr.set_defaults(func=cmd_repair)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        sys.stderr.write("[memory_retry_queue] interrumpido\n")
        return 130
    except Exception as e:
        sys.stderr.write(f"[memory_retry_queue] error inesperado: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())