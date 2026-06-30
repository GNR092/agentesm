#!/usr/bin/env python3
"""
agent_utils.py — Utilidades deterministicas para agentes opencode.

Subcomandos:
  now              -> YYYY-MM-DD HH:MM:SS TZ
  now-iso          -> 2026-06-30T14:32:11-03:00   (ISO 8601 con offset)
  now-unix         -> 1719761531                   (epoch seconds)
  now-rfc          -> Tue, 30 Jun 2026 14:32:11 -0300  (RFC 2822)
  session-id       -> DDMMMYYYY  (ej. 30junio2026)
  same-day N       -> mismo_dia | dia_diferente | ERR_INVALID_N
  weekday [N]      -> lunes|martes|miercoles|jueves|viernes|sabado|domingo
  is-weekend [N]   -> si | no
  add-days K [B]   -> DDMMMYYYY  (B = DDMMMYYYY o ISO o relativa, default hoy)
  diff-days A B    -> entero con signo (B - A)  (A,B tambien aceptan ISO o relativa)
  format-date [N]  -> DDMMMYYYY  (N = ISO, canonico o relativa; default hoy)
  parse-date N     -> YYYY-MM-DD  (N = DDMMMYYYY canonico)
  relative-date R  -> DDMMMYYYY  (R = frase relativa en espanol)
  next-weekday R   -> DDMMMYYYY  (R = lunes|martes|...  o  'proximo lunes')
  unavailable      -> [timestamp_no_disponible]

Frases relativas aceptadas (es, sin acentos obligatorios):
  hoy | ayer | anteayer/antier | manana | pasado manana
  hace N (dia|dias|semana|semanas|mes|meses)
  en   N (dia|dias|semana|semanas|mes|meses)
  proximo|proxima <dia_semana>   -> siguiente ocurrencia estrictamente futura
  pasado|pasada <dia_semana>     -> ultima ocurrencia estrictamente pasada

Zona horaria: detecta time.tzname del sistema (respeta env var TZ en
libc); si no esta disponible, cae a UTC. Sin archivos persistentes.

Salida: una sola linea por stdout. Exit codes:
  0 = ok
  2 = input invalido del usuario/agente (pre-existente)
  3 = fecha invalida en argumento

Sin acceso a disco fuera del propio script. Sin imports externos.
"""

import argparse
import datetime as dt
import sys
import time

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 fallback
    ZoneInfo = None

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

DIAS_ES = [
    "lunes", "martes", "miercoles", "jueves",
    "viernes", "sabado", "domingo",
]

MESES_ES_REV = {m: i + 1 for i, m in enumerate(MESES_ES)}


def resolve_tz_name():
    """Detecta nombre abreviado de TZ desde time.tzname.

    Devuelve string como 'CEST', 'EST', 'UTC'. Si time.tzname no
    devuelve nada util, devuelve 'UTC'.
    """
    try:
        name = time.tzname[0]
        if name and isinstance(name, str) and name.strip():
            return name.strip()
    except Exception:
        pass
    return "UTC"


def local_offset():
    """Offset local del sistema como timedelta, calculado a mano.

    Evita depender de ZoneInfo, que falla con abreviaturas ambiguas
    como 'CST' (China Standard Time vs Central Standard Time).
    """
    utc_now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    local_naive = dt.datetime.now()
    return local_naive - utc_now


def now_local():
    """Devuelve (dt_obj_con_offset, tz_name_str) en hora local del sistema.

    El datetime lleva tzinfo sintetico (timezone(offset)) para que
    utcoffset()/timestamp() funcionen correctamente.
    """
    tz_name = resolve_tz_name()
    offset = local_offset()
    tzinfo = dt.timezone(offset)
    ahora = dt.datetime.now(tzinfo)
    return ahora, tz_name


def format_offset(now):
    """Formato offset tipo -03:00 o +00:00."""
    offset = now.utcoffset()
    if offset is None or offset == dt.timedelta(0):
        return "+00:00"
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hh = total // 3600
    mm = (total % 3600) // 60
    return f"{sign}{hh:02d}:{mm:02d}"


def cmd_now(_args):
    ahora, tz_name = now_local()
    print(f"{ahora.strftime('%Y-%m-%d %H:%M:%S')} {tz_name}")
    return 0


def cmd_now_iso(_args):
    ahora, _ = now_local()
    print(f"{ahora.strftime('%Y-%m-%dT%H:%M:%S')}{format_offset(ahora)}")
    return 0


def cmd_now_unix(_args):
    ahora, _ = now_local()
    print(int(ahora.timestamp()))
    return 0


def cmd_now_rfc(_args):
    ahora, _ = now_local()
    offset_str = format_offset(ahora)
    weekday_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][ahora.weekday()]
    month_en = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][ahora.month - 1]
    sign = "-" if offset_str.startswith("-") else "+"
    hhmm = offset_str[1:]
    tz_2822 = f"{sign}{hhmm.replace(':', '')}"
    print(
        f"{weekday_en}, {ahora.day:02d} {month_en} {ahora.year:04d} "
        f"{ahora.hour:02d}:{ahora.minute:02d}:{ahora.second:02d} {tz_2822}"
    )
    return 0


def cmd_session_id(_args):
    ahora, _ = now_local()
    mes = MESES_ES[ahora.month - 1]
    print(f"{ahora.day}{mes}{ahora.year}")
    return 0


_MESES_CANONICOS = {
    "enero": 1, "ene": 1,
    "febrero": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "abril": 4, "abr": 4,
    "mayo": 5, "may": 5,
    "junio": 6, "jun": 6,
    "julio": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "septiembre": 9, "set": 9, "sept": 9,
    "octubre": 10, "oct": 10,
    "noviembre": 11, "nov": 11,
    "diciembre": 12, "dic": 12,
}
_MESES_CANONICOS_SORTED = sorted(_MESES_CANONICOS, key=len, reverse=True)


def parse_n(prev_n):
    """Parsea 'DDMMMYYYY' minuscula o ISO 'YYYY-MM-DD'. Devuelve date o None."""
    if not isinstance(prev_n, str) or len(prev_n) < 8:
        return None
    s = prev_n.strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            yyyy, mm, dd = int(s[:4]), int(s[5:7]), int(s[8:10])
            return dt.date(yyyy, mm, dd)
        except ValueError:
            return None
    s = s.lower()
    if len(s) < 9:
        return None
    dd_str = s[:2] if s[1].isdigit() else s[:1]
    rest = s[len(dd_str):]
    mes_encontrado = None
    mes_len = 0
    for mes in _MESES_CANONICOS_SORTED:
        if rest.startswith(mes):
            mes_encontrado = mes
            mes_len = len(mes)
            break
    if mes_encontrado is None:
        return None
    yyyy_str = rest[mes_len:]
    if len(yyyy_str) != 4 or not yyyy_str.isdigit():
        return None
    try:
        dd = int(dd_str)
        mm = _MESES_CANONICOS[mes_encontrado]
        yyyy = int(yyyy_str)
        return dt.date(yyyy, mm, dd)
    except (ValueError, KeyError):
        return None


def _strip_accents(s):
    """Quita acentos para matching tolerante: manana == mañana."""
    return (
        s.replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ü", "u")
    )


_SYNONYMS = {
    "anteayer": -2, "antier": -2, "antes de ayer": -2, "antesdeayer": -2,
    "ayer": -1,
    "hoy": 0,
    "manana": 1, "mañana": 1,
    "pasado manana": 2, "pasadomanana": 2, "pasado mañana": 2,
}

_DIAS_REV = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
    "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}

_UNIDADES = {
    "dia": 1, "dias": 1, "día": 1, "días": 1,
    "semana": 7, "semanas": 7,
    "mes": 30, "meses": 30,
    "anio": 365, "anios": 365, "año": 365, "años": 365,
}


def _add_months(fecha, n):
    """Suma N meses a fecha clampeando al último día del mes destino."""
    total_month = fecha.month - 1 + n
    year = fecha.year + total_month // 12
    month = total_month % 12 + 1
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    day = min(fecha.day, last_day)
    return dt.date(year, month, day)


def _parse_unit_offset(parts, today):
    """Procesa 'hace N <unidad>' o 'en N <unidad>'. parts = tokens."""
    if not parts:
        return None
    sign_word = parts[0]
    if sign_word not in ("hace", "en"):
        return None
    sign = -1 if sign_word == "hace" else 1
    if len(parts) < 2:
        return None
    num_word = parts[1]
    num = _parse_number_word(num_word)
    if num is None or num < 1:
        return None
    if len(parts) == 2:
        unit = "dia"
    elif len(parts) == 3:
        unit = _strip_accents(parts[2].lower())
        if unit not in _UNIDADES:
            return None
    else:
        return None
    delta_days = num * _UNIDADES[unit]
    if unit in ("mes", "meses"):
        return _add_months(today, sign * num)
    return today + dt.timedelta(days=sign * delta_days)


def _parse_number_word(word):
    """Convierte '3', 'tres', 'una', 'un', etc. a entero. None si falla."""
    w = word.lower()
    table = {
        "un": 1, "una": 1, "uno": 1,
        "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
        "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
        "once": 11, "doce": 12, "quince": 15, "veinte": 20,
    }
    if w in table:
        return table[w]
    if w.isdigit():
        return int(w)
    return None


def parse_rel_es(frase, today=None):
    """Parsea frase relativa en espanol. Devuelve date o None.

    Frases soportadas: ver docstring del modulo. today = fecha de
    referencia (default: hoy local del sistema).
    """
    if not frase or not isinstance(frase, str):
        return None
    if today is None:
        today = now_local()[0].date()
    s = _strip_accents(frase.strip().lower())
    s = " ".join(s.split())

    if s in _SYNONYMS:
        return today + dt.timedelta(days=_SYNONYMS[s])

    parts = s.split()
    if parts[0] in ("hace", "en"):
        return _parse_unit_offset(parts, today)

    if parts[0] in ("proximo", "proxima", "pasado", "pasada") and len(parts) == 2:
        direction = parts[0]
        dia_key = parts[1]
        target_wd = _DIAS_REV.get(dia_key)
        if target_wd is None:
            return None
        current_wd = today.weekday()
        if direction in ("proximo", "proxima"):
            delta = (target_wd - current_wd) % 7
            if delta == 0:
                delta = 7
            return today + dt.timedelta(days=delta)
        else:
            delta = (current_wd - target_wd) % 7
            if delta == 0:
                delta = 7
            return today - dt.timedelta(days=delta)

    if len(parts) == 1 and parts[0] in _DIAS_REV:
        target_wd = _DIAS_REV[parts[0]]
        current_wd = today.weekday()
        delta = (target_wd - current_wd) % 7
        if delta == 0:
            delta = 7
        return today + dt.timedelta(days=delta)

    return None


def parse_n_or_today(arg):
    """Parsea 'DDMMMYYYY', ISO 'YYYY-MM-DD' o frase relativa es.

    Cadena de fallback: canonico -> ISO -> relativa -> None.
    Si arg es None o vacio, devuelve hoy.
    """
    if not arg:
        return now_local()[0].date(), True
    parsed = parse_n(arg)
    if parsed is not None:
        return parsed, True
    try:
        iso = dt.date.fromisoformat(arg.strip())
        return iso, True
    except (ValueError, TypeError):
        pass
    rel = parse_rel_es(arg)
    if rel is not None:
        return rel, True
    return None, False


def format_n(fecha):
    """Convierte date a 'DDMMMYYYY' minuscula."""
    mes = MESES_ES[fecha.month - 1]
    return f"{fecha.day}{mes}{fecha.year}"


def cmd_same_day(args):
    if not args.prev_n:
        print("ERR_INVALID_N")
        return 2
    prev_date = parse_n(args.prev_n)
    if prev_date is None:
        print("ERR_INVALID_N")
        return 2
    ahora, _ = now_local()
    if prev_date == ahora.date():
        print("mismo_dia")
    else:
        print("dia_diferente")
    return 0


def cmd_weekday(args):
    fecha, ok = parse_n_or_today(args.n)
    if not ok:
        print("ERR_INVALID_DATE")
        return 3
    print(DIAS_ES[fecha.weekday()])
    return 0


def cmd_is_weekend(args):
    fecha, ok = parse_n_or_today(args.n)
    if not ok:
        print("ERR_INVALID_DATE")
        return 3
    print("si" if fecha.weekday() >= 5 else "no")
    return 0


def cmd_add_days(args):
    try:
        k = int(args.k)
    except (TypeError, ValueError):
        print("ERR_INVALID_K")
        return 2
    fecha, ok = parse_n_or_today(args.base)
    if not ok:
        print("ERR_INVALID_DATE")
        return 3
    nueva = fecha + dt.timedelta(days=k)
    print(format_n(nueva))
    return 0


def cmd_diff_days(args):
    a, ok_a = parse_n_or_today(args.a if hasattr(args, "a") else None)
    if not ok_a:
        print("ERR_INVALID_DATE")
        return 3
    b, ok_b = parse_n_or_today(args.b if hasattr(args, "b") else None)
    if not ok_b:
        print("ERR_INVALID_DATE")
        return 3
    delta = (b - a).days
    print(delta)
    return 0


def cmd_format_date(args):
    fecha, ok = parse_n_or_today(args.n)
    if not ok:
        print("ERR_INVALID_DATE")
        return 3
    print(format_n(fecha))
    return 0


def cmd_parse_date(args):
    fecha = parse_n(args.n)
    if fecha is None:
        print("ERR_INVALID_DATE")
        return 3
    print(fecha.isoformat())
    return 0


def cmd_relative_date(args):
    """Convierte frase relativa en espanol a canonico DDMMMYYYY."""
    if not args.r:
        print("ERR_INVALID_DATE")
        return 3
    fecha = parse_rel_es(args.r)
    if fecha is None:
        print("ERR_INVALID_DATE")
        return 3
    print(format_n(fecha))
    return 0


def cmd_next_weekday(args):
    """Convierte 'proximo lunes' o 'lunes' (dia de la semana) a fecha canonica.

    Acepta 'lunes'|'proximo lunes'|'pasado lunes'. Acepta tildes.
    """
    if not args.r:
        print("ERR_INVALID_DATE")
        return 3
    s = _strip_accents(args.r.strip().lower())
    s = " ".join(s.split())
    if s.startswith("proximo ") or s.startswith("proxima "):
        fecha = parse_rel_es(s)
        if fecha is None:
            print("ERR_INVALID_DATE")
            return 3
        print(format_n(fecha))
        return 0
    if s.startswith("pasado ") or s.startswith("pasada "):
        fecha = parse_rel_es(s)
        if fecha is None:
            print("ERR_INVALID_DATE")
            return 3
        print(format_n(fecha))
        return 0
    if s in _DIAS_REV:
        fecha = parse_rel_es("proximo " + s)
        if fecha is None:
            print("ERR_INVALID_DATE")
            return 3
        print(format_n(fecha))
        return 0
    print("ERR_INVALID_DATE")
    return 3


def cmd_unavailable(_args):
    print("[timestamp_no_disponible]")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="agent_utils.py",
        description="Utilidades deterministicas (timestamp, fechas) para agentes opencode.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("now", help="Imprime timestamp actual ISO con TZ") \
        .set_defaults(func=cmd_now)
    sub.add_parser("now-iso", help="Imprime timestamp ISO 8601 con offset") \
        .set_defaults(func=cmd_now_iso)
    sub.add_parser("now-unix", help="Imprime epoch en segundos") \
        .set_defaults(func=cmd_now_unix)
    sub.add_parser("now-rfc", help="Imprime timestamp en formato RFC 2822") \
        .set_defaults(func=cmd_now_rfc)
    sub.add_parser("session-id", help="Imprime N de sesion en formato DDMMMYYYY") \
        .set_defaults(func=cmd_session_id)

    p_sd = sub.add_parser(
        "same-day",
        help="Compara un N previo con la fecha actual",
    )
    p_sd.add_argument("prev_n", help="N previo en formato DDMMMYYYY")
    p_sd.set_defaults(func=cmd_same_day)

    p_wd = sub.add_parser(
        "weekday",
        help="Dia de la semana en espanol (lunes..domingo)",
    )
    p_wd.add_argument("n", nargs="?", default=None,
                      help="Fecha opcional DDMMMYYYY (default: hoy)")
    p_wd.set_defaults(func=cmd_weekday)

    p_iw = sub.add_parser(
        "is-weekend",
        help="Devuelve si|no si cae sabado/domingo",
    )
    p_iw.add_argument("n", nargs="?", default=None,
                      help="Fecha opcional DDMMMYYYY (default: hoy)")
    p_iw.set_defaults(func=cmd_is_weekend)

    p_ad = sub.add_parser(
        "add-days",
        help="Suma K dias (puede ser negativo) y devuelve DDMMMYYYY",
    )
    p_ad.add_argument("k", help="Entero con signo (ej. 3, -7)")
    p_ad.add_argument("base", nargs="?", default=None,
                      help="Fecha base DDMMMYYYY (default: hoy)")
    p_ad.set_defaults(func=cmd_add_days)

    p_dd = sub.add_parser(
        "diff-days",
        help="Dias entre dos fechas (B - A). Default de A y B = hoy",
    )
    p_dd.add_argument("a", nargs="?", default=None, help="Fecha A")
    p_dd.add_argument("b", nargs="?", default=None, help="Fecha B")
    p_dd.set_defaults(func=cmd_diff_days)

    p_fd = sub.add_parser(
        "format-date",
        help="Convierte una fecha ISO 'YYYY-MM-DD' a canonico DDMMMYYYY",
    )
    p_fd.add_argument("n", nargs="?", default=None,
                      help="Fecha ISO 'YYYY-MM-DD' (default: hoy)")
    p_fd.set_defaults(func=cmd_format_date)

    p_pd = sub.add_parser(
        "parse-date",
        help="Convierte una fecha canonica DDMMMYYYY a ISO 'YYYY-MM-DD'",
    )
    p_pd.add_argument("n", help="Fecha canonica DDMMMYYYY")
    p_pd.set_defaults(func=cmd_parse_date)

    p_rd = sub.add_parser(
        "relative-date",
        help="Convierte frase relativa en espanol a DDMMMYYYY")
    p_rd.add_argument("r", help="Frase relativa (ej. ayer, hace 3 dias)")
    p_rd.set_defaults(func=cmd_relative_date)

    p_nw = sub.add_parser(
        "next-weekday",
        help="Resuelve 'proximo lunes' o 'lunes' a DDMMMYYYY")
    p_nw.add_argument("r", help="Dia (ej. lunes, proximo viernes, pasado lunes)")
    p_nw.set_defaults(func=cmd_next_weekday)

    sub.add_parser(
        "unavailable",
        help="Imprime el literal de fallback cuando el script no esta disponible",
    ).set_defaults(func=cmd_unavailable)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"ERR_INTERNAL: {type(e).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
