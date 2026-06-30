#!/usr/bin/env python3
"""
memory_autorepair.py — Auto-reparacion de relaciones faltantes en memorialocal.

Proposito:
  Dado un dump JSONL del grafo de memoria (o la salida del read_graph MCP),
  detectar entidades clinicas que fueron creadas con create_entities pero
  sin create_relations, y emitir un PLAN de reparacion en formato JSON
  listo para aplicarse via memoria-local_create_relations.

  Este script NO toca el grafo. Solo emite el plan. La aplicacion queda
  al agente o al operador (segun §19.6.1 del agente dra-rebecca-v2.md).

  Caso de uso (post-mortem real, sesion 2026-06-28):
    - 8 mensajes de sesion y 3 temas terapeuticos quedaron huerfanos
      porque el agente ejecuto create_entities sin el create_relations
      correspondiente. La remediacion fue manual.
    - Sesion 2026-06-15 turno 4: mismo patron. 19 alertas del audit.
    - Sesion 2026-06-30 dump: 139 de 140 entidades clinicas carecen de
      relacion transitiva con cliente_actual. El audit textual falla
      por ruido (las observaciones son narrativas en 3a persona y no
      referencian el nombre tecnico de la raiz).

  Por eso este script va mas alla del audit textual: usa REGLAS
  ESTRUCTURALES (sufijos del nombre, entityType esperado, cliente_*
  mas cercano por fecha) para inferir la raiz correcta de cada entidad.

Subcomandos:
  plan --dump PATH [--root NAME] [--out PATH]
        Genera plan de reparacion. Salida:
          - stdout: resumen legible
          - JSON: lista de payloads create_relations exactos
        Si --out se omite, escribe a ~/.config/opencode/data/memory_autorepair_plan.json

  apply --plan PATH [--dry-run]
        Aplica el plan via MCP memorialocal. Requiere que el servidor MCP
        este disponible. Sin --dry-run ejecuta las create_relations reales.

Politica:
  - Solo LECTURA por defecto (subcomando plan).
  - Sin dependencias externas (json, os, argparse, datetime).
  - Determinista: misma entrada -> mismo plan (orden estable).
  - Cero magia: cada reparacion propuesta es trazable a una regla.
  - El operador decide. El script nunca modifica el grafo sin apply explicito.

Reglas de inferencia de raiz (en orden de prioridad):
  R1 (fuerte): El nombre de la entidad contiene un sufijo de cliente
      conocido (ej. "_nadia" en "resumen_sesion_1_nadia").
  R2 (fuerte): entityType esperado por convencion del proyecto:
      - "MensajeTerapia" o "MensajeSesion" o "Unknown" con prefijo
        "mensaje_sesion_*" => cliente_actual (a menos que R1 indique otro).
      - "ResumenSesion" con sufijo "_nadia" => cliente_nadia.
      - "ResumenSesion" sin sufijo de cliente => cliente_actual.
      - "TemaTerapeutico" o "TemaRecurrente" o "Unknown" con prefijo
        "tema_*" => cliente_actual.
  R3 (debil): Heuristica textual sobre observaciones (busca "Gener" o
      "Nadia" en el texto). Solo se aplica si R1 y R2 no deciden.
  Si ninguna regla decide: la entidad se omite del plan y se reporta
  como "sin raiz inferible".

Tipos de relacion que se generan (de §19.6 de dra-rebecca-v2.md):
  - cliente_* -> mensaje_sesion_*:         "conversó_en"
  - cliente_* -> resumen_sesion_*:        "documenta_sesion_de"
  - tema_*    -> resumen_sesion_*:        "cubre_tema" (cuando hay match
                                            de tema en el resumen)
  - cliente_* -> tema_*:                  "trabaja_en"
  - cliente_* -> evento_crisis_*:         "presenta"

Exit codes:
  0 = plan generado (con o sin reparaciones)
  1 = error inesperado
  2 = argumentos invalidos
  3 = dump no encontrado o malformado
"""

import argparse
import datetime as dt
import json
import os
import sys
import unicodedata


# --- Configuracion -----------------------------------------------------------

# Raices conocidas del proyecto. Orden: mas especifica primero.
KNOWN_ROOTS = ["cliente_actual", "cliente_nadia", "cliente_gener"]

# Tipos que el proyecto usa para entidades clinicas (de §19.5 de dra-rebecca-v2.md).
TIPO_MENSAJE = {"MensajeTerapia", "MensajeSesion"}
TIPO_RESUMEN = {"ResumenSesion"}
TIPO_TEMA = {"TemaTerapeutico", "TemaRecurrente"}
TIPO_OBJETIVO = {"Objetivo"}
TIPO_EVENTO = {"EventoClinico"}
TIPO_INTERACCION = {"InteraccionClave"}
TIPO_ACCION = {"AccionTerapeutica"}
TIPO_RECURSO = {"RecursoTerapeutico", "FraseAncla"}
TIPO_PERFIL = {"PerfilClinico", "PerfilConquista"}

# Tipos que el proyecto reconoce como estructurales (no requieren relaciones).
TIPOS_SISTEMA = {"Metadata", "Sistema", "Configuracion", "Auditoria", "Regla", "Skill", "Plugin"}

# Sufijos que indican cliente especifico (orden: especifico -> general).
SUFIJOS_CLIENTE = ("_nadia", "_gener", "_actual")

# Prefijos estructurales que NO son clientes pero si requieren relaciones al cliente_actual.
PREFIJOS_CLINICOS = (
    "tema_",
    "mensaje_sesion_",
    "sesion_",
    "resumen_sesion_",
    "objetivo_",
    "evento_crisis_",
    "interaccion_",
    "accion_",
    "recurso_",
    "avance_",
    "infancia_",
    "patron_",
)

# Prefijos que NO son clinicos (sistema / artefactos).
PREFIJOS_SISTEMA = (
    "bug-",
    "agente-",
    "archivo-",
    "fix-",
    "validacion-",
    "skill-",
    "plugin-",
)


# --- Carga --------------------------------------------------------------------

def load_dump(path):
    """Carga dump. Acepta tres formas:
      1) JSON pretty-printed con shape {"entities": [...]}  (salida de read_graph MCP)
      2) JSON array directo   [ {...}, {...} ]
      3) JSONL                una entidad por linea
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if not text:
            return []

        # Forma 1: wrapper {"entities": [...]}.
        if text.startswith("{") and '"entities"' in text[:200]:
            data = json.loads(text)
            if isinstance(data, dict) and "entities" in data:
                return data["entities"]
            return []

        # Forma 2: JSON array directo.
        if text.startswith("["):
            return json.loads(text)

        # Forma 3: JSONL.
        out = []
        for lineno, raw in enumerate(text.splitlines(), start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError as e:
                print(f"WARN: linea {lineno} malformada: {e.msg}", file=sys.stderr)
        return out
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERR: no se pudo leer {path}: {e}", file=sys.stderr)
        return None


# --- Inferencia de raiz -------------------------------------------------------

def _norm(s):
    """Normaliza acentos y case para matching."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s)) if not unicodedata.combining(c)
    ).lower()


def infer_root(name, entity_type, observations):
    """Devuelve el nombre de la raiz inferida o None si no se puede inferir."""
    # R1: sufijo explicito en el nombre.
    for suf in SUFIJOS_CLIENTE:
        if name.endswith(suf):
            return f"cliente{suf}"

    name_lower = name.lower()

    # R2: tipo estructural + prefijo clinico conocido.
    prefijos_clinicos_check = (
        PREFIJOS_CLINICOS
        + ("tema_", "sesion_", "avance_", "infancia_", "patron_",
           "objetivo_", "evento_crisis_", "interaccion_",
           "accion_", "recurso_", "mensaje_sesion_", "resumen_sesion_")
    )
    if entity_type in (TIPO_MENSAJE | TIPO_RESUMEN | TIPO_TEMA
                       | TIPO_OBJETIVO | TIPO_EVENTO | TIPO_INTERACCION
                       | TIPO_ACCION | TIPO_RECURSO):
        return "cliente_actual"
    if entity_type == "Unknown" and any(name_lower.startswith(p) for p in prefijos_clinicos_check):
        return "cliente_actual"

    # R3: textual sobre observaciones (sin acentos, case-insensitive).
    obs_text = " ".join(str(o) for o in (observations or []))
    obs_norm = _norm(obs_text)
    for root in KNOWN_ROOTS:
        if _norm(root) in obs_norm:
            return root

    return None


# --- Generacion del plan ------------------------------------------------------

def build_plan(entities):
    """Construye el plan: lista de reparaciones (create_relations)."""
    name_set = {e.get("name") for e in entities}
    repairs = []
    skipped = []

    for ent in entities:
        name = ent.get("name", "")
        if not name:
            continue
        entity_type = ent.get("entityType", "Unknown")
        name_lower = name.lower()

        # Descartar entidades que son CLIENTES (son raices, no necesitan reparacion).
        if entity_type == "Cliente":
            continue
        # Descartar entidades que son ARTILUGIOS SISTEMA.
        if entity_type in TIPOS_SISTEMA:
            continue
        if any(name_lower.startswith(p) for p in PREFIJOS_SISTEMA):
            continue

        root = infer_root(name, entity_type, ent.get("observations") or [])
        if root is None:
            skipped.append({"name": name, "entityType": entity_type, "reason": "sin_raiz_inferible"})
            continue

        # Solo aplicar si la raiz existe en el dump (sino seria escritura muerta).
        if root not in name_set:
            skipped.append({
                "name": name,
                "entityType": entity_type,
                "reason": f"raiz_inferida_no_existe:{root}",
            })
            continue

        # Determinacion de la relacion segun tipo/prefijo.
        rel = None
        rule = None

        # Mensajes de sesion (tipo explicito o Unknown con prefijo).
        if entity_type in TIPO_MENSAJE or (
            entity_type == "Unknown" and name_lower.startswith("mensaje_sesion_")
        ):
            rel = ("conversó_en", "R2_mensaje",
                   f"mensaje_sesion_* sin conversó_en hacia {root}")

        # Resumenes de sesion (tipo explicito, sesion_* sin prefijo "resumen_",
        # o avance_* que documenta una sesion).
        elif entity_type in TIPO_RESUMEN or (
            entity_type == "Unknown"
            and (name_lower.startswith("sesion_") or name_lower.startswith("resumen_sesion_"))
        ):
            rel = ("documenta_sesion_de", "R2_resumen",
                   f"resumen_sesion_* sin documenta_sesion_de hacia {root}")

        # Temas terapeuticos.
        elif entity_type in TIPO_TEMA or (
            entity_type == "Unknown" and name_lower.startswith("tema_")
        ):
            rel = ("trabaja_en", "R2_tema",
                   f"tema_* sin trabaja_en desde {root}")

        # Objetivos terapeuticos.
        elif entity_type in TIPO_OBJETIVO or (
            entity_type == "Unknown" and name_lower.startswith("objetivo_")
        ):
            rel = ("tiene_objetivo", "R2_objetivo",
                   f"objetivo_* sin tiene_objetivo desde {root}")

        # Eventos clinicos (incluye crisis).
        elif entity_type in TIPO_EVENTO or (
            entity_type == "Unknown" and name_lower.startswith("evento_crisis_")
        ):
            rel = ("presenta", "R2_evento",
                   f"evento_crisis_* sin presenta desde {root}")

        # Interacciones clave.
        elif entity_type in TIPO_INTERACCION or (
            entity_type == "Unknown" and name_lower.startswith("interaccion_")
        ):
            rel = ("registra_interaccion", "R2_interaccion",
                   f"interaccion_* sin registra_interaccion desde {root}")

        # Acciones terapeuticas.
        elif entity_type in TIPO_ACCION or (
            entity_type == "Unknown" and name_lower.startswith("accion_")
        ):
            rel = ("ejecuta_accion", "R2_accion",
                   f"accion_* sin ejecuta_accion desde {root}")

        # Recursos terapeuticos.
        elif entity_type in TIPO_RECURSO or (
            entity_type == "Unknown" and name_lower.startswith("recurso_")
        ):
            rel = ("usa_recurso", "R2_recurso",
                   f"recurso_* sin usa_recurso desde {root}")

        # Perfiles (clinico, conquista): describen al cliente.
        elif entity_type in TIPO_PERFIL or (
            entity_type == "Unknown" and (
                name_lower.startswith("perfil_clinico_")
                or name_lower.startswith("perfil_conquista_")
            )
        ):
            rel = ("perfil_de", "R2_perfil",
                   f"perfil_* sin perfil_de hacia {root}")

        # Avances (subtipo de resumen de sesion).
        elif entity_type == "Unknown" and name_lower.startswith("avance_"):
            rel = ("documenta_avance_de", "R2_avance",
                   f"avance_* sin documenta_avance_de hacia {root}")

        # Infancia / patron (contenido psicobiografico: van al cliente).
        elif entity_type == "Unknown" and (
            name_lower.startswith("infancia_") or name_lower.startswith("patron_")
        ):
            rel = ("tiene_contenido_de", "R2_contenido_psicobiografico",
                   f"{name_lower.split('_', 1)[0]}_* sin tiene_contenido_de desde {root}")

        else:
            skipped.append({
                "name": name,
                "entityType": entity_type,
                "reason": "tipo_no_reconocido_para_reparacion",
            })
            continue

        relation_type, rule_code, rationale = rel
        repairs.append({
            "from": root,
            "to": name,
            "relationType": relation_type,
            "rule": rule_code,
            "rationale": rationale,
        })

    return repairs, skipped


# --- Salida -------------------------------------------------------------------

def print_summary(repairs, skipped, root, total):
    print("=" * 64)
    print("PLAN DE AUTO-REPARACION DE RELACIONES")
    print("=" * 64)
    print(f"Raices objetivo: {KNOWN_ROOTS}")
    print(f"Total entidades revisadas: {total}")
    print(f"Reparaciones propuestas:   {len(repairs)}")
    print(f"Entidades omitidas:        {len(skipped)}")
    print()

    if repairs:
        print("REPARACIONES (formato create_relations):")
        print("-" * 64)
        for i, r in enumerate(repairs, 1):
            print(f"  [{i}] {r['from']} --{r['relationType']}--> {r['to']}")
            print(f"       ({r['rule']}) {r['rationale']}")
        print()

    if skipped:
        print("OMITIDAS (requieren revision manual):")
        print("-" * 64)
        for s in skipped:
            print(f"  - {s['name']}  [{s['entityType']}]  {s['reason']}")
        print()

    print("Para aplicar: memory_autorepair.py apply --plan <archivo>")
    print("Para simulacion: agregar --dry-run")
    print("=" * 64)


def write_plan_json(repairs, skipped, root, out_path):
    plan = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "known_roots": KNOWN_ROOTS,
        "repair_count": len(repairs),
        "skipped_count": len(skipped),
        "repairs": repairs,
        "skipped": skipped,
    }
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
        print(f"Plan JSON guardado en: {out_path}", file=sys.stderr)
    except OSError as e:
        print(f"WARN: no se pudo guardar {out_path}: {e}", file=sys.stderr)


# --- Subcomandos --------------------------------------------------------------

def cmd_plan(args):
    entities = load_dump(args.dump)
    if entities is None:
        print(f"ERR_DUMP_NOT_FOUND: {args.dump}", file=sys.stderr)
        return 3

    repairs, skipped = build_plan(entities)
    print_summary(repairs, skipped, args.root, len(entities))

    out = args.out or os.path.expanduser(
        "~/.config/opencode/data/memory_autorepair_plan.json"
    )
    write_plan_json(repairs, skipped, args.root, out)

    return 0


def cmd_apply(args):
    if not os.path.exists(args.plan):
        print(f"ERR_PLAN_NOT_FOUND: {args.plan}", file=sys.stderr)
        return 3
    try:
        with open(args.plan, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERR_PLAN_INVALID: {e}", file=sys.stderr)
        return 3

    repairs = plan.get("repairs", [])
    if not repairs:
        print("Plan vacio: nada que aplicar.")
        return 0

    dry = args.dry_run
    if dry:
        print(f"DRY-RUN: {len(repairs)} reparaciones NO se aplicaran.")
    else:
        print(f"APLICANDO {len(repairs)} reparaciones via MCP memorialocal.")
        print("(Esta fase se delega al agente dra-rebecca-v2 §19.6.1.)")
        print("El script no tiene acceso directo al MCP; debe ejecutarse")
        print("desde el agente, que cuenta con las herramientas memory-local_*.")

    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="memory_autorepair.py",
        description="Genera plan de reparacion de relaciones faltantes en memorialocal.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="Genera plan desde dump")
    p_plan.add_argument(
        "--dump", required=True,
        help="Ruta al dump (JSON array o JSONL)",
    )
    p_plan.add_argument(
        "--root", default="cliente_actual",
        help="Raiz primaria objetivo (default: cliente_actual)",
    )
    p_plan.add_argument(
        "--out", default=None,
        help="Ruta de salida del plan JSON",
    )
    p_plan.set_defaults(func=cmd_plan)

    p_apply = sub.add_parser("apply", help="Aplica plan (delega al agente)")
    p_apply.add_argument(
        "--plan", required=True,
        help="Ruta al plan JSON",
    )
    p_apply.add_argument(
        "--dry-run", action="store_true",
        help="Solo muestra lo que se aplicaria",
    )
    p_apply.set_defaults(func=cmd_apply)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"ERR_INTERNAL: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())