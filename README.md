# AGENTS.md

Índice de los agentes definidos en este directorio. Cada archivo `.md` aquí es un agente invocable por opencode.

## Estructura del repositorio

- `*.md` — definición de agentes (uno por archivo).
- `.codesearch.db/` — base del índice semántico local (ignorada por git).
- `.search/` — caché de búsquedas web (ignorada).
- `investigacion/` — artefactos generados por los agentes investigadores (ignorada).
- `data/` — datos auxiliares (ignorada).
- `scripts/` — utilidades auxiliares.

## Reglas globales (aplican a todos los agentes de este repo)

1. **No inventar librerías.** Verificar `package.json`, `Cargo.toml`, `pyproject.toml`, `composer.json`, `pom.xml` antes de usar una dependencia.
2. **Respetar convenciones del código existente.** No reformatear ni renombrar sin que se pida.
3. **Sin comentarios no solicitados.** No añadir comentarios al código a menos que el usuario lo pida.
4. **Sin commits implícitos.** Solo el agente `@git` commitea, y solo cuando el usuario lo solicite.
5. **Cambios scoped.** Cualquier cambio fuera del alcance declarado → registro de observaciones, no ejecución.
6. **Cero alucinaciones.** Si una fuente no se puede verificar → marcar como `unknown`, no inferir.
7. **Idioma.** Español por defecto. Mantener respuestas concisas; el detalle va en artefactos o memoria.

## Modos

| Modo | Significado |
|------|-------------|
| `primary` | Agente principal, se invoca directamente como `@nombre` o por defecto. |
| `subagent` | Agente auxiliar, se delega desde un agente primary o se invoca como `@nombre`. |

## Agentes primary

| Agente | Archivo | Descripción |
|--------|---------|-------------|
| `@code` | [`code.md`](code.md) | Asistente general de ingeniería de software. Ejecuta tareas, escribe código, sigue convenciones. Breve y directo. |
| `@debug` | [`debug.md`](debug.md) | Investigación estricta de fallos. Solo analiza, no modifica código. Memoria persistente, máximo 3 hipótesis, una a la vez. |
| `@fix` | [`fix.md`](fix.md) | Aplica planes ya aprobados (fixes o features). Modifica código solo dentro del alcance del plan. |
| `@test` | [`test.md`](test.md) | Testing no destructivo. Solo se ejecuta bajo solicitud explícita. Valida fixes ya aplicados. |
| `@agente-plan` | [`agente-plan.md`](agente-plan.md) | Planificación. Modo A: plan de fix desde causa raíz. Modo B: plan de feature/mejora. No modifica código. |
| `@cambio-quirurgico` | [`cambio-quirurgico.md`](cambio-quirurgico.md) | Ejecuta exactamente un cambio puntual declarado. No auto-corrige ni expande scope. Hallazgos fuera de alcance → observaciones. |

## Agentes subagent

| Agente | Archivo | Descripción |
|--------|---------|-------------|
| `@git` | [`git.md`](git.md) | Operaciones Git: commits, push, pull, merge, rebase, tags. Mensajes en español sin prefijos. Pide confirmación reforzada para operaciones destructivas. |
| `@docker` | [`docker.md`](docker.md) | Docker y Docker Compose. Inspección primero, confirmación reforzada para `down -v`, `prune`, `rm`, `rmi`, etc. |
| `@versionador` | [`versionador.md`](versionador.md) | Propone el siguiente número SemVer desde el historial git y Conventional Commits. Solo inspección, dry-run obligatorio. |
| `@Investigador-Cientifico` | [`Investigador-Cientifico.md`](Investigador-Cientifico.md) | Investigación científica sobre psicología, neurobiología y sociología de la atracción humana. Solo fuentes peer-reviewed, académicas `.edu` o `.gov`. |
| `@Investigador-Secundario` | [`Investigador-Secundario.md`](Investigador-Secundario.md) | Investigación científica sobre un tema indicado por contexto. Mismo rigor que `@Investigador-Cientifico`. |

## Permisos especiales

Solo algunos agentes tienen permisos `permission:` declarados. Todos los demás operan con los permisos por defecto del usuario.

| Agente | Permisos relevantes |
|--------|---------------------|
| `@git` | `git *` permitido; `rebase`, `push --force`, `push --mirror`, `branch -D`, `tag -d/-f`, `reset`, `clean`, `commit --amend`, `--no-verify` requieren `ask`. |
| `@docker` | `docker *` y `docker compose *` permitidos; `down -v`, `prune`, `rm`, `rmi`, `kill`, `volume rm`, `network rm`, `exec --privileged`, `image prune`, `build --push` requieren `ask`. |
| `@versionador` | Solo lectura: `git log/status/tag -l/show/diff/rev-parse/describe` permitidos. `edit`, `git push`, `git tag -d/-f`, `webfetch` denegados. Todo lo demás `ask`. |

## Skills usadas por los agentes

| Skill | Agentes que la invocan |
|-------|------------------------|
| `agent-strategies` | `@code` (al inicio de sesión) |
| `commit-msg` | `@git` (al inicio de sesión) |
| `code-search` | `@code`, `@debug` (búsqueda avanzada) |
| `memory-sync` | `@code`, `@debug`, `@fix`, `@test`, `@agente-plan` (memoria persistente) |
| `token-efficient-workflow` | `@code` (orquestación) |
| `postgresqldb` | `@code` (guía PostgreSQL) |
| `ci4-expert` | `@code` (CodeIgniter 4) |
| `interface-design` | `@code` (dashboards, admin panels) |
| `docx-generator` | `@code` (documentos `.docx`/`.pdf`) |
| `erp-e2e-tester` | `@code` (pruebas E2E módulo de compras) |

## Flujos de trabajo entre agentes

- **Bug fix**: `@debug` → `@agente-plan` (modo A) → `@fix` → `@test`.
- **Feature/mejora**: `@agente-plan` (modo B) → `@fix` → `@test`.
- **Cambio puntual bien definido**: `@cambio-quirurgico`.
- **Investigación científica**:
  - Atracción humana → `@Investigador-Cientifico`.
  - Otro tema → `@Investigador-Secundario`.
- **Release / versionado**: `@versionador` (análisis) → humano decide → `@git` (tag + push).
- **Operaciones de infraestructura**: `@docker`, `@git`.

## Convenciones de memoria

Los agentes primary (`@debug`, `@fix`, `@test`, `@agente-plan`) usan `{memory_prefix}*` para sincronizar hallazgos, planes y resultados con el knowledge graph persistente. `@cambio-quirurgico` y `@code` pueden usarlo opcionalmente.