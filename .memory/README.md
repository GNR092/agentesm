---
disable: true
---

# Fallback de Memoria Persistente — `.memory/`

Esta carpeta actúa como **respaldo offline** cuando el MCP de memoria persistente no está disponible, no responde o una llamada `{memory_prefix}*` falla.

Cualquier agente que deba guardar un plan, hallazgo, hipótesis, bug, feature o relación, puede escribir aquí en vez de (o además de) la memoria MCP. Otros agentes pueden leer estos archivos para continuar el trabajo.

> **Ubicación:** los agentes crean y usan `.memory/` en el **working directory del proyecto actual** (no en el directorio de configuración de opencode). El archivo que estás leyendo es la plantilla de convención.

## Convención de archivos

```
.memory/
├── README.md            ← este archivo
├── entities/            ← un archivo .md por entidad
│   ├── bug-42.md
│   ├── hipotesis-H1.md
│   ├── plan-01.md
│   └── feature-export-csv.md
└── relations.md         ← relaciones dirigidas entre entidades
```

### Archivo de entidad

Cada entidad vive en `entities/<nombre-entidad>.md` con este formato obligatorio:

```markdown
---
entity: bug-42
type: bug
---

- Estado: CONFIRMADA
- Archivo: src/Controller.php:142
- Conclusión: descripción del hallazgo
- Observación adicional: ...
```

- `entity`: nombre único de la entidad (igual al nombre del archivo sin `.md`).
- `type`: tipo de entidad (`bug`, `hipotesis`, `plan`, `feature`, `fix`, `test`, `tema`, `fuente`, `proyecto`, etc.).
- Cada bullet (`- `) es una observación.

### Archivo de relaciones

`relations.md` guarda relaciones dirigidas entre entidades:

```markdown
# Relaciones del knowledge graph

bug-42 -> caused_by -> hipotesis-H1
hipotesis-H1 -> found_in -> archivo:src/Controller.php:142
bug-42 -> tiene_plan -> plan-01
plan-01 -> implementado_por -> fix-01
fix-01 -> validado_por -> test-01
```

Formato de cada línea:

```
<origen> -> <tipo-relacion> -> <destino>
```

No modificar una relación existente a menos que sea para corregirla; añadir nuevas líneas al final.

## Reglas para agentes

1. **Intentar memoria MCP primero.** Si las herramientas `{memory_prefix}*` están disponibles, úsalas como fuente principal.
2. **Si la memoria MCP falla** (error, timeout, tool no disponible, servidor no responde), usar `.memory/` como fallback.
3. **Crear la carpeta si no existe.** Antes de escribir, asegurar que existen `.memory/entities/` y `.memory/relations.md`.
4. **No duplicar entidades sin necesidad.** Si una entidad ya existe, añadir observaciones al archivo en vez de crear otro.
5. **Mantener relaciones sincronizadas.** Cada vez que se crea una entidad, añadir al menos una relación en `relations.md` para evitar nodos huérfanos.
6. **Compartir entre agentes.** Si un agente escribe un plan, otro agente (por ejemplo, `03-fix.md`) puede leerlo de `.memory/entities/plan-*.md` y de `relations.md`.

## Ejemplo de uso

Guardar una hipótesis confirmada:

```markdown
# Archivo: .memory/entities/hipotesis-H1.md
---
entity: hipotesis-H1
type: hipotesis
---

- Estado: CONFIRMADA
- Confianza: Alto
- Conclusión: la excepción ocurre porque el servicio no valida el campo X antes de llamar a Y
- Archivo: src/Service.php:87
```

Actualizar relaciones:

```markdown
# .memory/relations.md
bug-42 -> has_hypothesis -> hipotesis-H1
hipotesis-H1 -> found_in -> archivo:src/Service.php:87
```

Leer planes previos: listar `.memory/entities/plan-*.md`, leer el más reciente o el que se relacione con el bug/feature actual a través de `relations.md`.
