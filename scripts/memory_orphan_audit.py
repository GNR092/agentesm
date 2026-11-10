#!/usr/bin/env python3
"""
memory_orphan_audit.py — Auditoria de entidades huerfanas en memorialocal.

Proposito:
  Detectar entidades clinicas que NO estan conectadas transitivamente a
  una entidad raiz declarada (ej. cliente_actual). Estas entidades son
  "huérfanas": existen en el grafo pero el agente no las puede recuperar
  por traversée desde la raiz, así que sus datos no llegan al contexto
  de la sesion.

  Este script solo lee el grafo; nunca crea, repara ni borra relaciones.
  El reporte incluye nombres, tipos y conteos, nunca observaciones.

Subcomandos:
  audit --root <entity_name> [--server memory|memory-local] [--dump PATH]
        Con --server consulta read_graph. Sin --server usa el dump JSONL.
        Si el grafo contiene relaciones, usa traversal dirigido; si no,
        el dump conserva la heuristica textual historica.

  from-dump --dump PATH --root <entity_name> [--out PATH]
        Audita un dump JSON/JSONL local.

  session-close --root <entity_name> --server memory|memory-local
        Cuenta el cierre autenticado por raiz y audita cada 5 sesiones.

Ubicacion del dump esperado (formato JSONL):
  ~/.config/opencode/data/memory_graph.jsonl
  Cada linea: {"name": "...", "entityType": "...", "observations": [...]}

Politica:
  - read_graph es la unica llamada MCP; no se imprime ni persiste su dump.
  - La configuracion MCP se lee de opencode.json o opencode.jsonc.
  - El contador guarda solo el hash de la raiz y conteos, no datos clinicos.
  - El grafo nunca se modifica.
  - Salida deterministica: misma entrada -> mismo reporte (orden estable).
  - Codigos de salida:
      0 = no hay huerfanos (o los huerfanos detectados son solo ruido)
      1 = huerfanos detectados (se imprime resumen accionable)
      2 = argumentos invalidos
      3 = dump no encontrado o malformado
      4 = error de MCP o del contador

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
import contextlib
import fcntl
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


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

CONFIG_PATHS = (
    Path.home() / ".config" / "opencode" / "opencode.json",
    Path.home() / ".config" / "opencode" / "opencode.jsonc",
)
DATA_DIR = Path.home() / ".config" / "opencode" / "data"
COUNTER_PATH = DATA_DIR / "memory_orphan_audit_sessions.json"


def _strip_jsonc(text):
    """Quita comentarios y comas finales JSONC sin alterar strings."""
    out = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        else:
            out.append(c)
        i += 1

    text = "".join(out)
    out = []
    i, n, in_string = 0, len(text), False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
        elif c == '"':
            in_string = True
            out.append(c)
        elif c == ",":
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            if j < n and text[j] in "]}":
                i += 1
                continue
            out.append(c)
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _normalize_graph(data):
    """Devuelve (entidades, relaciones); None indica dump sin relaciones."""
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and isinstance(data.get("entities"), list):
        relations = data.get("relations")
        if relations is not None and not isinstance(relations, list):
            raise ValueError("relaciones invalidas")
        return data["entities"], relations
    if isinstance(data, dict) and data.get("name"):
        return [data], None
    raise ValueError("formato de grafo no soportado")


def load_dump(path):
    """Carga JSON de grafo, array o JSONL sin exponer observaciones."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
    except OSError as e:
        print(f"ERR: no se pudo leer {path}: {e}", file=sys.stderr)
        return None
    if not text:
        return [], None
    try:
        return _normalize_graph(json.loads(text))
    except json.JSONDecodeError:
        entities = []
        malformed = False
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                entities.append(json.loads(raw))
            except json.JSONDecodeError as e:
                print(f"WARN: linea {lineno} malformada: {e.msg}", file=sys.stderr)
                malformed = True
        return None if malformed else (entities, None)
    except ValueError:
        print("ERR: formato de grafo no soportado", file=sys.stderr)
        return None


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


def find_orphans(entities, root_name, relations=None):
    """Detecta entidades no alcanzables por relaciones dirigidas desde root.

    Solo los dumps antiguos sin relaciones usan la heuristica textual.
    """
    orphans = []
    reachable = {root_name}
    if relations is not None:
        adjacency = defaultdict(list)
        for relation in relations:
            if isinstance(relation, dict):
                source, target = relation.get("from"), relation.get("to")
                if isinstance(source, str) and isinstance(target, str):
                    adjacency[source].append(target)
        pending = [root_name]
        while pending:
            for target in adjacency.get(pending.pop(), []):
                if target not in reachable:
                    reachable.add(target)
                    pending.append(target)

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        name = entity.get("name", "")
        if not name:
            continue
        if name == root_name:
            continue
        if is_sistema(entity):
            continue

        if relations is not None:
            if name in reachable:
                continue
        else:
            # Compatibilidad para dumps antiguos sin lista de relaciones.
            obs = entity.get("observations") or []
            if root_name and root_name in " ".join(str(o) for o in obs):
                continue

        observations = entity.get("observations")
        orphans.append({
            "name": name,
            "entityType": entity.get("entityType", "Unknown"),
            "observation_count": len(observations) if isinstance(observations, list) else 0,
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
            lines.append("")
        lines.append("ACCION RECOMENDADA:")
        lines.append("  Revisar si cada entidad debe tener relacion con la raiz.")
        lines.append("  Confirme y repare manualmente solo las relaciones que correspondan.")
        lines.append("  Si no: dejar la entidad sin cambios.")
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


def load_mcp_config(server, config_paths=CONFIG_PATHS):
    """Carga solo el servidor solicitado y omite entradas deshabilitadas."""
    for path in config_paths:
        try:
            config = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
        except OSError:
            continue
        except json.JSONDecodeError:
            raise RuntimeError("configuracion MCP invalida") from None
        entry = (config.get("mcp") or {}).get(server)
        if (not isinstance(entry, dict) or entry.get("enabled") is False
                or not isinstance(entry.get("url"), str) or not entry["url"]):
            continue
        return {
            "url": entry["url"],
            "headers": entry.get("headers") if isinstance(entry.get("headers"), dict) else {},
        }
    raise RuntimeError("servidor MCP no disponible")


def _parse_mcp_body(raw):
    raw = raw.strip()
    if not raw:
        raise ValueError("respuesta MCP vacia")
    if raw[0] in "{[":
        return json.loads(raw)
    for line in raw.splitlines():
        if line.strip().startswith("data:"):
            data = line.strip()[5:].strip()
            if data and data != "[DONE]":
                return json.loads(data)
    raise ValueError("respuesta MCP no parseable")


def _extract_graph(message):
    """Desenvuelve la respuesta MCP; no acepta entidades sin relaciones."""
    result = message.get("result", message) if isinstance(message, dict) else None
    if not isinstance(result, dict) or "error" in message:
        raise ValueError("read_graph fallo")
    if result.get("isError"):
        raise ValueError("read_graph fallo")

    graph = result.get("structuredContent")
    if graph is None:
        graph = result if isinstance(result.get("entities"), list) else None
    if graph is None:
        for block in result.get("content", []):
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                try:
                    graph = json.loads(block["text"])
                except json.JSONDecodeError:
                    continue
                break
    if isinstance(graph, str):
        graph = json.loads(graph)
    entities, relations = _normalize_graph(graph)
    if relations is None:
        raise ValueError("read_graph sin relaciones")
    if any(not isinstance(entity, dict) or not isinstance(entity.get("name"), str)
           for entity in entities):
        raise ValueError("entidades MCP invalidas")
    if any(not isinstance(relation, dict)
           or not isinstance(relation.get("from"), str)
           or not isinstance(relation.get("to"), str)
           for relation in relations):
        raise ValueError("relaciones MCP invalidas")
    return entities, relations


def read_live_graph(server):
    """Invoca exclusivamente read_graph mediante MCP Streamable HTTP."""
    config = load_mcp_config(server)

    def post(payload, session_id=None):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **config["headers"],
        }
        if session_id:
            headers["mcp-session-id"] = session_id
        with tempfile.NamedTemporaryFile(delete=False, suffix=".hdr") as header_file:
            header_path = header_file.name
        command = ["curl", "-sS", "--max-time", "30", "-X", "POST", "-D", header_path]
        for key, value in headers.items():
            command.extend(("-H", f"{key}: {value}"))
        command.extend(("--data-binary", json.dumps(payload), config["url"]))
        try:
            response = subprocess.run(command, capture_output=True, text=True, timeout=40)
            if response.returncode:
                raise RuntimeError("solicitud MCP fallida")
            try:
                raw_headers = Path(header_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                raw_headers = ""
            return response.stdout, raw_headers
        finally:
            try:
                os.unlink(header_path)
            except OSError:
                pass

    _, raw_headers = post({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "memory-orphan-audit", "version": "1.0"},
        },
    })
    session_id = None
    for line in raw_headers.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            if key.strip().lower() == "mcp-session-id" and value.strip():
                session_id = value.strip()
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    raw, _ = post({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "read_graph", "arguments": {}},
    }, session_id)
    return _extract_graph(_parse_mcp_body(raw))


def _update_counter(root, state_path=COUNTER_PATH, audited_count=None):
    """Guarda conteos por hash de raiz bajo lock; nunca el identificador."""
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_fd = os.open(str(state_path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            state = {"version": 1, "roots": {}}
        except json.JSONDecodeError:
            raise RuntimeError("contador de sesiones invalido") from None
        if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("roots"), dict):
            raise RuntimeError("contador de sesiones invalido")

        key = hashlib.sha256(root.encode("utf-8")).hexdigest()
        entry = state["roots"].setdefault(key, {"count": 0, "audited": 0})
        if not isinstance(entry, dict) or not isinstance(entry.get("count"), int):
            raise RuntimeError("contador de sesiones invalido")
        entry.setdefault("audited", 0)
        if audited_count is None:
            entry["count"] += 1
        else:
            entry["audited"] = max(entry["audited"], min(audited_count, entry["count"]))

        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=state_path.parent, delete=False) as tmp:
            json.dump(state, tmp)
            temp_path = tmp.name
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, state_path)
        return entry["count"], entry["audited"]
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _report(root, entities, relations, out_path=None):
    orphans = find_orphans(entities, root, relations)
    print_report(root, len(entities), orphans, out_path)
    return 1 if orphans else 0


def _audit_live(root, server, out_path=None):
    try:
        entities, relations = read_live_graph(server)
    except Exception:
        print("ERR_MCP: no se pudo auditar el grafo vivo", file=sys.stderr)
        return 4
    return _report(root, entities, relations, out_path)


def cmd_audit(args):
    if args.server:
        if args.dump:
            print("ERR_ARGS: --dump y --server son excluyentes", file=sys.stderr)
            return 2
        return _audit_live(args.root, args.server, args.out)

    dump_path = args.dump or os.path.expanduser(
        "~/.config/opencode/data/memory_graph.jsonl"
    )
    graph = load_dump(dump_path)
    if graph is None:
        print(f"ERR_DUMP_NOT_FOUND: {dump_path}", file=sys.stderr)
        return 3
    entities, relations = graph
    return _report(args.root, entities, relations, args.out)


def cmd_from_dump(args):
    graph = load_dump(args.dump)
    if graph is None:
        print(f"ERR_DUMP_INVALID: {args.dump}", file=sys.stderr)
        return 3
    entities, relations = graph
    return _report(args.root, entities, relations, args.out)


def cmd_session_close(args):
    try:
        count, audited = _update_counter(args.root)
    except Exception:
        print("ERR_COUNTER: no se pudo actualizar el contador", file=sys.stderr)
        return 4
    if count - audited < 5:
        print(f"Sesiones autenticadas desde la ultima auditoria: {count - audited}/5")
        return 0

    print("Auditoria periodica de solo lectura:")
    result = _audit_live(args.root, args.server)
    if result in (0, 1):
        try:
            _update_counter(args.root, audited_count=count)
        except Exception:
            print("WARN: no se pudo registrar la auditoria en el contador", file=sys.stderr)
            return 4
    return result


def cmd_self_test(_args):
    marker = "DATO_CLINICO_SINTETICO_NO_IMPRIMIR"
    graph = {
        "entities": [
            {"name": "cliente_demo", "entityType": "Cliente", "observations": []},
            {"name": "perfil_demo", "entityType": "PerfilClinico", "observations": [marker]},
            {"name": "mensaje_demo", "entityType": "MensajeTerapia", "observations": []},
            {"name": "tema_aislado", "entityType": "TemaTerapeutico", "observations": [f"perfil_demo {marker}"]},
            {"name": "catalog_index", "entityType": "Metadata", "observations": []},
        ],
        "relations": [
            {"from": "perfil_demo", "to": "cliente_demo", "relationType": "resume"},
            {"from": "cliente_demo", "to": "mensaje_demo", "relationType": "conversó_en"},
            {"from": "tema_aislado", "to": "perfil_demo", "relationType": "referencia"},
        ],
    }
    response = {"result": {"content": [{"type": "text", "text": json.dumps(graph)}]}}
    entities, relations = _extract_graph(response)
    expected = [{"name": "tema_aislado", "entityType": "TemaTerapeutico", "observation_count": 1}]
    assert find_orphans(entities, "perfil_demo", relations) == expected

    with tempfile.TemporaryDirectory() as directory:
        dump = Path(directory) / "graph.json"
        dump.write_text(json.dumps(graph), encoding="utf-8")
        loaded_entities, loaded_relations = load_dump(dump)
        assert find_orphans(loaded_entities, "perfil_demo", loaded_relations) == expected
        out = Path(directory) / "report.json"
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            print_report("perfil_demo", len(entities), expected, out)
            assert cmd_from_dump(argparse.Namespace(
                dump=str(dump), root="cliente_demo", out=None,
            )) == 1
        report_text = out.read_text(encoding="utf-8")
        assert marker not in report_text and marker not in output.getvalue()
        assert marker not in errors.getvalue()
        assert "tema_aislado" in report_text

        legacy = Path(directory) / "legacy.jsonl"
        legacy.write_text(json.dumps({
            "name": "tema_legacy", "entityType": "TemaTerapeutico",
            "observations": ["mencion de cliente_demo en datos sinteticos"],
        }) + "\n", encoding="utf-8")
        legacy_entities, legacy_relations = load_dump(legacy)
        assert legacy_relations is None
        assert find_orphans(legacy_entities, "cliente_demo", legacy_relations) == []

        state = Path(directory) / "counter.json"
        assert _update_counter("cliente_demo", state) == (1, 0)
        assert _update_counter("cliente_demo", state) == (2, 0)
        assert "cliente_demo" not in state.read_text(encoding="utf-8")

        config = Path(directory) / "opencode.jsonc"
        config.write_text(
            '{/*synthetic*/"mcp":{"memory-local":{"enabled":false,"url":"https://unused.invalid"},'
            '"memory":{"url":"https://example.invalid","headers":{"Authorization":"synthetic"}}}}',
            encoding="utf-8",
        )
        try:
            load_mcp_config("memory-local", [config])
            raise AssertionError("servidor deshabilitado aceptado")
        except RuntimeError:
            pass
        assert load_mcp_config("memory", [config])["url"] == "https://example.invalid"

    try:
        _extract_graph({"result": {"content": [{
            "type": "text", "text": json.dumps({"entities": graph["entities"]}),
        }]}})
        raise AssertionError("grafo sin relaciones aceptado")
    except ValueError:
        pass

    assert json.loads(_strip_jsonc('{/*comment*/"mcp":{"memory":{"url":"x",},},}'))
    print("self-test: ok")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="memory_orphan_audit.py",
        description="Auditoria de solo lectura de entidades huerfanas.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser("audit", help="Audita un grafo vivo o dump local")
    p_audit.add_argument("--root", required=True, help="Nombre de la entidad raiz")
    p_audit.add_argument("--dump", default=None, help="Ruta a dump JSON/JSONL")
    p_audit.add_argument("--server", choices=("memory", "memory-local"), default=None,
                         help="Servidor MCP; activa read_graph sin guardar el dump")
    p_audit.add_argument("--out", default=None, help="Ruta para guardar solo el reporte")
    p_audit.set_defaults(func=cmd_audit)

    p_fd = sub.add_parser("from-dump", help="Audita un dump local")
    p_fd.add_argument("--dump", required=True, help="Ruta al dump JSON/JSONL")
    p_fd.add_argument("--root", required=True, help="Nombre de la entidad raiz")
    p_fd.add_argument("--out", default=None, help="Ruta para guardar solo el reporte")
    p_fd.set_defaults(func=cmd_from_dump)

    p_close = sub.add_parser("session-close", help="Cuenta una sesion autenticada y audita cada cinco")
    p_close.add_argument("--root", required=True, help="Raiz clinica autenticada")
    p_close.add_argument("--server", choices=("memory", "memory-local"), default="memory-local")
    p_close.set_defaults(func=cmd_session_close)

    p_test = sub.add_parser("self-test", help="Pruebas con un grafo sintetico")
    p_test.set_defaults(func=cmd_self_test)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"ERR_INTERNAL: {type(e).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
