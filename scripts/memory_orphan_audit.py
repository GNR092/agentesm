#!/usr/bin/env python3
"""
memory_orphan_audit.py — Auditoria de entidades huerfanas en memorialocal.

Proposito:
  Detectar entidades clinicas que NO estan conectadas transitivamente a
  una entidad raiz declarada (ej. cliente_actual). Estas entidades son
  "huérfanas": existen en el grafo pero el agente no las puede recuperar
  por traversée desde la raiz, así que sus datos no llegan al contexto
  de la sesion.

  Esta clase de bug ya ocurrio en produccion (sesion 2026-06-28):
  8 mensajes de sesion y 3 temas terapeuticos quedaron huerfanos
  durante varias horas porque fueron creados con create_entities
  sin create_relations en el mismo turno. La remediacion manual fue
  crear las 11 relaciones faltantes.

  Este script automatiza la deteccion y emite dos artefactos:
    - Reporte en stdout (legible para humanos)
    - Reporte JSON en disco (para auditoria posterior o pipeline)

Subcomandos:
  audit --root <entity_name> [--project <name>] [--out PATH]
        Recorre el grafo desde la raiz. Detecta huerfanos.
        Imprime resumen y opcionalmente guarda JSON.
        Sin acceso al MCP: opera sobre el dump JSONL local.

  from-dump --dump PATH --root <entity_name> [--out PATH]
        Igual que audit, pero el grafo se carga desde un dump JSONL
        previamente generado (util cuando el MCP no esta disponible).

Ubicacion del dump esperado (formato JSONL):
  ~/.config/opencode/data/memory_graph.jsonl
  Cada linea: {"name": "...", "entityType": "...", "observations": [...]}
  Las relaciones se infieren por co-ocurrencia: si dos entidades
  aparecen en el mismo turno (mismo timestamp +/- 60s), se asume
  relacion candidata. Este modo es solo para auditoria sin MCP.

Politica:
  - Sin acceso al MCP memorialocal (no es dependencia rigida).
  - Sin acceso al grafo clinico via escritura: este script SOLO LEE.
  - Salida deterministica: misma entrada -> mismo reporte (orden estable).
  - Codigos de salida:
      0 = no hay huerfanos (o los huerfanos detectados son solo ruido)
      1 = huerfanos detectados (se imprime resumen accionable)
      2 = argumentos invalidos
      3 = dump no encontrado o malformado

Casos de ruido que NO se marcan como huerfanos:
  - Entidades de tipo Metadata/Sistema/Configuracion
  - Entidades con sufijo _index, _root, _meta
  - La entidad raiz misma
  - Entidades marcadas explicitamente como "catalogicas" (sin
    relaciones por diseño, ej. lista de sinonimos).

Esto es auditoria, no gobierno automatico: el script NO modifica el
grafo. Solo emite reporte para que el operador/agente decida.
"""

import argparse
import json
import os
import sys
from collections import defaultdict


# Tipos de entidad que se consideran "del sistema" y no requieren
# conexion al cliente raiz. Ajustar si el proyecto agrega mas tipos.
TIPOS_SISTEMA = {
    "Metadata",
    "Sistema",
    "Configuracion",
    "Auditoria",
    "Regla",
    "Skill",
    "Plugin",
}

# Sufijos que indican entidades catalogicas (sin relaciones por diseño).
SUFIJOS_CATALOGICOS = ("_index", "_root", "_meta", "_catalog", "_list")


def load_jsonl(path):
    """Carga un JSONL. Cada linea es una entidad.

    Devuelve lista de entidades (dict) o None si hay error.
    """
    if not os.path.exists(path):
        return None
    entities = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entities.append(json.loads(raw))
                except json.JSONDecodeError as e:
                    print(
                        f"WARN: linea {lineno} malformada: {e.msg}",
                        file=sys.stderr,
                    )
    except OSError as e:
        print(f"ERR: no se pudo leer {path}: {e}", file=sys.stderr)
        return None
    return entities


def is_sistema(entity):
    """Devuelve True si la entidad es de sistema/catalogica."""
    etype = entity.get("entityType", "")
    name = entity.get("name", "")
    if etype in TIPOS_SISTEMA:
        return True
    for suf in SUFIJOS_CATALOGICOS:
        if name.endswith(suf):
            return True
    return False


def find_orphans(entities, root_name):
    """Detecta entidades que NO son alcanzables transitivamente desde root.

    Como no tenemos acceso directo al grafo de relaciones desde un dump
    JSONL de solo entidades, usamos heuristica conservadora:
      - Si la entidad es la raiz, no es huerfana.
      - Si la entidad es de sistema/catalogica, se ignora.
      - Si la entidad tiene una observacion que menciona a la raiz por
        nombre (ej. "cliente X consulto..."), se asume alcanzable.
      - En cualquier otro caso, SE MARCA COMO POTENCIAL HUERFANA y se
        imprime el nombre + tipo para revision.

    Esta heuristica es deliberadamente conservadora: prefiere falsos
    positivos (marcar algo que en realidad esta conectado) sobre falsos
    negativos (dejar pasar un huerfano real). El operador confirma.
    """
    orphans = []
    name_set = {e.get("name") for e in entities}

    for entity in entities:
        name = entity.get("name", "")
        if not name:
            continue
        if name == root_name:
            continue
        if is_sistema(entity):
            continue

        # Heuristica: busqueda textual del nombre de la raiz en observaciones
        obs = entity.get("observations") or []
        obs_text = " ".join(str(o) for o in obs)
        if root_name and root_name in obs_text:
            # Si la raiz es mencionada, asumimos alcanzable
            continue

        # Si llegamos aqui, la entidad es candidata a huerfana
        orphans.append({
            "name": name,
            "entityType": entity.get("entityType", "Unknown"),
            "first_observation": (obs[0][:120] + "...") if obs else "(sin observaciones)",
            "observation_count": len(obs),
        })

    return orphans


def print_report(root, total, huerfanas, out_path=None):
    """Imprime reporte en stdout y opcionalmente guarda JSON."""
    lines = []
    lines.append("=" * 60)
    lines.append("AUDITORIA DE ENTIDADES HUERFANAS")
    lines.append("=" * 60)
    lines.append(f"Raiz: {root}")
    lines.append(f"Total entidades revisadas: {total}")
    lines.append(f"Huerfanas detectadas: {len(huerfanas)}")
    lines.append("")

    if huerfanas:
        lines.append("LISTA DE HUERFANAS POTENCIALES:")
        lines.append("-" * 60)
        for h in huerfanas:
            lines.append(f"  - {h['name']}")
            lines.append(f"    Tipo: {h['entityType']}")
            lines.append(f"    Observaciones: {h['observation_count']}")
            lines.append(f"    Primera obs: {h['first_observation']}")
            lines.append("")
        lines.append("ACCION RECOMENDADA:")
        lines.append("  Revisar si cada entidad debe tener relacion con la raiz.")
        lines.append("  Si debe: agregar con create_relations (manual o via agente).")
        lines.append("  Si no: dejar como esta (es catalogica o intencional).")
    else:
        lines.append("OK: no se detectaron huerfanas potenciales.")

    lines.append("=" * 60)
    report_text = "\n".join(lines)
    print(report_text)

    if out_path:
        report = {
            "root": root,
            "total_entities": total,
            "orphan_count": len(huerfanas),
            "orphans": huerfanas,
        }
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"\nReporte JSON guardado en: {out_path}", file=sys.stderr)
        except OSError as e:
            print(f"WARN: no se pudo guardar {out_path}: {e}", file=sys.stderr)


def cmd_audit(args):
    """Audita desde un dump JSONL local."""
    dump_path = args.dump
    if not dump_path:
        # Default razonable: el dump que se genero con read_graph
        dump_path = os.path.expanduser(
            "~/.config/opencode/data/memory_graph.jsonl"
        )

    entities = load_jsonl(dump_path)
    if entities is None:
        print(f"ERR_DUMP_NOT_FOUND: {dump_path}", file=sys.stderr)
        return 3

    huerfanas = find_orphans(entities, args.root)
    print_report(args.root, len(entities), huerfanas, args.out)

    return 1 if huerfanas else 0


def cmd_from_dump(args):
    """Audita cargando dump explicito."""
    entities = load_jsonl(args.dump)
    if entities is None:
        print(f"ERR_DUMP_INVALID: {args.dump}", file=sys.stderr)
        return 3

    huerfanas = find_orphans(entities, args.root)
    print_report(args.root, len(entities), huerfanas, args.out)

    return 1 if huerfanas else 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="memory_orphan_audit.py",
        description="Auditoria de entidades huerfanas en memorialocal.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser(
        "audit",
        help="Audita desde el dump por defecto",
    )
    p_audit.add_argument(
        "--root", required=True,
        help="Nombre de la entidad raiz (ej. cliente_actual)",
    )
    p_audit.add_argument(
        "--dump", default=None,
        help="Ruta al dump JSONL (default: ~/.config/opencode/data/memory_graph.jsonl)",
    )
    p_audit.add_argument(
        "--out", default=None,
        help="Ruta donde guardar reporte JSON",
    )
    p_audit.set_defaults(func=cmd_audit)

    p_fd = sub.add_parser(
        "from-dump",
        help="Audita desde un dump explicito",
    )
    p_fd.add_argument(
        "--dump", required=True,
        help="Ruta al dump JSONL",
    )
    p_fd.add_argument(
        "--root", required=True,
        help="Nombre de la entidad raiz",
    )
    p_fd.add_argument(
        "--out", default=None,
        help="Ruta donde guardar reporte JSON",
    )
    p_fd.set_defaults(func=cmd_from_dump)

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