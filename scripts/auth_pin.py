#!/usr/bin/env python3
"""
auth_pin.py - Sistema de autenticacion por PIN hasheado para agentes opencode.

Uso:
    auth_pin.py set <client_id> <pin>
    auth_pin.py verify <client_id> <pin>
    auth_pin.py exists <client_id>     # YES/NO leyendo pins.json (fuente de verdad)
    auth_pin.py delete <client_id>      # Alias de 'reset' sin confirmacion
    auth_pin.py reset <client_id> --confirm
    auth_pin.py list

Output (stdout) - solo strings simples, NUNCA hashes ni sales:
    OK
    YES                          # solo en subcomando 'exists'
    NO                           # solo en subcomando 'exists'
    ERR_INVALID_PIN
    ERR_LOCKED_OUT: <segundos>
    ERR_NO_PIN_SET
    ERR_PIN_TOO_SHORT
    ERR_CLIENT_EXISTS
    ERR_MISSING_ARG
    ERR_CORRUPT_FILE
    ERR_RATE_LIMITED_INTERNAL

Los errores tecnicos se escriben a stderr.

Importante: 'exists' es la fuente de verdad autoritativa para decisiones de
seguridad (ej. distingir Caso A vs Caso B en el flujo de configuracion inicial
del PIN). NO usar busqueda semantica de memoria para esa bifurcacion, porque
su umbral es configurable y discrecional, y puede omitir perfiles reales.
"""

import argparse
import errno
import hashlib
import hmac
import json
import os
import secrets
import stat
import sys
import time
from pathlib import Path

DATA_DIR = Path.home() / ".config" / "opencode" / "data"
PINS_FILE = DATA_DIR / "pins.json"
LOCKOUT_FILE = DATA_DIR / "lockout.json"

# Parametros OWASP para scrypt
SCRYPT_N = 32768       # 2^15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SALT_BYTES = 16
MIN_PIN_LEN = 8

# Rate limiting progresivo
LOCKOUT_BASE_SECONDS = 15 * 60   # 15 minutos
LOCKOUT_MAX_SECONDS = 24 * 60 * 60  # tope 24h


def log_err(msg):
    print(msg, file=sys.stderr)


def ensure_data_dir():
    """Crea el directorio de datos con permisos 0700 y los JSONs con 0600."""
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, mode=0o700)
        try:
            os.chmod(DATA_DIR, 0o700)
        except OSError as e:
            log_err(f"WARN: no se pudieron aplicar 0700 al directorio: {e}")
    # Por si existe con permisos mas laxos
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass

    for f in (PINS_FILE, LOCKOUT_FILE):
        if not f.exists():
            f.write_text("{}", encoding="utf-8")
        try:
            os.chmod(f, 0o600)
        except OSError as e:
            log_err(f"WARN: no se pudieron aplicar 0600 a {f}: {e}")


def load_json(path, label):
    """Carga un JSON o falla con ERR_CORRUPT_FILE sin sobrescribir."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        log_err(f"ERROR: {label} corrupto ({path}): {e}")
        return None
    if not isinstance(data, dict):
        log_err(f"ERROR: {label} no es un objeto JSON valido")
        return None
    return data


def save_json(path, data):
    """Guarda un JSON atomicamente con permisos 0600."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError as e:
        log_err(f"WARN: chmod 0600 en {tmp}: {e}")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError as e:
        log_err(f"WARN: chmod 0600 en {path}: {e}")


# OpenSSL exige un maxmem explicito >= 32 MiB para los parametros OWASP.
# Por defecto hashlib.scrypt calcula un valor menor y falla con
# "digital envelope routines: memory limit exceeded" en muchas builds.
SCRYPT_MAXMEM = 64 * 1024 * 1024  # 64 MiB, holgado para n=2^15


def hash_pin(pin, salt):
    """Devuelve hash scrypt(salt + pin)."""
    return hashlib.scrypt(
        pin.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )


def compute_hash(pin):
    """Genera (salt_b64, hash_b64) para un PIN nuevo."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hash_pin(pin, salt)
    return (
        salt.hex(),
        digest.hex(),
    )


def lockout_remaining(lockout_state, client_id, now):
    """Devuelve segundos restantes de bloqueo, o 0 si no esta bloqueado."""
    rec = lockout_state.get(client_id)
    if not rec:
        return 0
    until = rec.get("locked_until", 0)
    if not until or now >= until:
        return 0
    return int(until - now)


def next_lockout_seconds(failed_count):
    """Duplica el tiempo de bloqueo con cada intento fallido, con tope."""
    # failed_count incluye el intento que esta fallando ahora
    # 5to fallo -> 15min, 6to -> 30min, 7mo -> 60min, ...
    extras = max(0, failed_count - 5)
    secs = LOCKOUT_BASE_SECONDS * (2 ** extras)
    return min(secs, LOCKOUT_MAX_SECONDS)


def cmd_set(args):
    pin = args.pin
    client_id = args.client_id
    if len(pin) < MIN_PIN_LEN:
        print("ERR_PIN_TOO_SHORT")
        return 0

    ensure_data_dir()
    pins = load_json(PINS_FILE, "pins.json")
    if pins is None:
        print("ERR_CORRUPT_FILE")
        return 0
    lockout = load_json(LOCKOUT_FILE, "lockout.json")
    if lockout is None:
        print("ERR_CORRUPT_FILE")
        return 0

    if client_id in pins:
        print("ERR_CLIENT_EXISTS")
        return 0

    salt_hex, hash_hex = compute_hash(pin)
    pins[client_id] = {
        "salt": salt_hex,
        "hash": hash_hex,
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "dklen": SCRYPT_DKLEN,
        "created": int(time.time()),
    }
    save_json(PINS_FILE, pins)
    # Limpiar cualquier lockout previo si existia
    if client_id in lockout:
        del lockout[client_id]
        save_json(LOCKOUT_FILE, lockout)

    print("OK")
    return 0


def cmd_exists(args):
    """Comprueba si existe un PIN configurado para <client_id>.

    Lee pins.json (0600) directamente. NO expone hashes, sales ni timestamps.
    Es la fuente de verdad autoritativa para decisiones de seguridad
    (bifurcacion Caso A vs Caso B en el flujo de configuracion inicial del PIN):
    su salida es un contrato binario trivialmente parseable, NO juicio
    discrecional sobre busqueda semantica de memoria.

    Output:
        YES    -> existe registro para ese client_id
        NO     -> no existe registro
        ERR_CORRUPT_FILE -> pins.json no es un objeto JSON valido
    """
    client_id = args.client_id
    ensure_data_dir()
    pins = load_json(PINS_FILE, "pins.json")
    if pins is None:
        print("ERR_CORRUPT_FILE")
        return 0
    if client_id in pins:
        print("YES")
    else:
        print("NO")
    return 0


def cmd_verify(args):
    client_id = args.client_id
    pin = args.pin
    now = int(time.time())

    ensure_data_dir()
    pins = load_json(PINS_FILE, "pins.json")
    if pins is None:
        print("ERR_CORRUPT_FILE")
        return 0
    lockout = load_json(LOCKOUT_FILE, "lockout.json")
    if lockout is None:
        print("ERR_CORRUPT_FILE")
        return 0

    if client_id not in pins:
        print("ERR_NO_PIN_SET")
        return 0

    # Comprobar bloqueo activo
    rem = lockout_remaining(lockout, client_id, now)
    if rem > 0:
        print(f"ERR_LOCKED_OUT: {rem}")
        return 0

    rec = pins[client_id]
    try:
        salt = bytes.fromhex(rec["salt"])
        expected = bytes.fromhex(rec["hash"])
    except (KeyError, ValueError) as e:
        log_err(f"ERROR: registro corrupto para {client_id}: {e}")
        print("ERR_CORRUPT_FILE")
        return 0

    candidate = hash_pin(pin, salt)
    if hmac.compare_digest(candidate, expected):
        # Limpiar intentos fallidos al tener exito
        if client_id in lockout:
            del lockout[client_id]
            save_json(LOCKOUT_FILE, lockout)
        print("OK")
        return 0

    # PIN incorrecto -> registrar fallo y posiblemente bloquear
    entry = lockout.get(client_id, {"failed": 0, "locked_until": 0})
    entry["failed"] = entry.get("failed", 0) + 1
    failed = entry["failed"]

    if failed >= 5:
        secs = next_lockout_seconds(failed)
        entry["locked_until"] = now + secs
        lockout[client_id] = entry
        save_json(LOCKOUT_FILE, lockout)
        print(f"ERR_LOCKED_OUT: {secs}")
        return 0

    lockout[client_id] = entry
    save_json(LOCKOUT_FILE, lockout)
    print("ERR_INVALID_PIN")
    return 0


def cmd_delete(args):
    """Elimina PIN sin confirmacion (pensado para flujos automatizados)."""
    client_id = args.client_id
    ensure_data_dir()
    pins = load_json(PINS_FILE, "pins.json")
    if pins is None:
        print("ERR_CORRUPT_FILE")
        return 0
    lockout = load_json(LOCKOUT_FILE, "lockout.json")
    if lockout is None:
        print("ERR_CORRUPT_FILE")
        return 0

    if client_id not in pins:
        print("ERR_NO_PIN_SET")
        return 0

    del pins[client_id]
    save_json(PINS_FILE, pins)
    if client_id in lockout:
        del lockout[client_id]
        save_json(LOCKOUT_FILE, lockout)
    print("OK")
    return 0


def cmd_reset(args):
    client_id = args.client_id
    if not args.confirm:
        log_err("ERROR: reset requiere --confirm")
        print("ERR_MISSING_ARG")
        return 2
    return cmd_delete(argparse.Namespace(client_id=client_id))


def cmd_list(args):
    ensure_data_dir()
    pins = load_json(PINS_FILE, "pins.json")
    if pins is None:
        print("ERR_CORRUPT_FILE")
        return 0
    if not pins:
        return 0
    # Solo IDs y timestamp, nunca hashes ni sales
    for cid in sorted(pins.keys()):
        ts = pins[cid].get("created", 0)
        # Formato: client_id<TAB>timestamp (ISO si queremos, epoch aqui)
        print(f"{cid}\t{ts}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="auth_pin.py",
        description="Autenticacion por PIN hasheado (scrypt) para agentes opencode.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set", help="Configurar o reemplazar PIN")
    p_set.add_argument("client_id")
    p_set.add_argument("pin")
    p_set.set_defaults(func=cmd_set)

    p_verify = sub.add_parser("verify", help="Verificar PIN")
    p_verify.add_argument("client_id")
    p_verify.add_argument("pin")
    p_verify.set_defaults(func=cmd_verify)

    p_exists = sub.add_parser(
        "exists",
        help="Comprobar existencia de PIN (YES/NO). Fuente de verdad autoritativa.",
    )
    p_exists.add_argument("client_id")
    p_exists.set_defaults(func=cmd_exists)

    p_delete = sub.add_parser("delete", help="Eliminar PIN (sin confirmacion)")
    p_delete.add_argument("client_id")
    p_delete.set_defaults(func=cmd_delete)

    p_reset = sub.add_parser("reset", help="Resetear PIN (requiere --confirm)")
    p_reset.add_argument("client_id")
    p_reset.add_argument("--confirm", action="store_true",
                         help="Confirmacion explicita requerida")
    p_reset.set_defaults(func=cmd_reset)

    p_list = sub.add_parser("list", help="Listar clientes con PIN")
    p_list.set_defaults(func=cmd_list)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # ultimo recurso: nunca filtrar secretos
        log_err(f"ERROR interno: {e}")
        print("ERR_RATE_LIMITED_INTERNAL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
