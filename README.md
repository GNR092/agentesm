---
disable: true
---

# AGENTS.md

Índice de los agentes definidos en este directorio. Cada archivo `.md` aquí es un agente invocable por opencode.

## Descripción del repositorio

Este repo contiene una colección de agentes especializados para operaciones de ingeniería de software, investigación, testing y versionado. Los agentes están organizados en dos categorías principales:

- **Agentes primary** — equipos principales que procesan tareas de forma autónoma desde el estado inicial hasta la finalización. Trabajan directamente bajo solicitud del usuario y pueden modificar código, generar cambios, ejecutar tests y aplicar los resultados de investigación.

- **Subagentes** — ayudantes especializados para tareas específicas (`@git`, `@docker`, `@versionador`, `@Investigador-Cientifico`, `@Investigador-Secundario`). Se invocan desde agentes primary o directamente por el usuario para ejecutar comandos de bajo nivel, introspección o validación de evidencia.

Los agentes siguen un flujo de trabajo estructurado (debug → plan → fix → test) para el ciclo de corrección de errores, y un flujo de trabajo separado para features/mejoras. Todos los agentes mantienen un estado persistente utilizando un knowledge graph unificado, lo que permite una ejecución consistente y transparente entre sesiones.

## Estructura del repositorio

La estructura física del repo se organiza en:

```
*.md                       # Definiciones de agentes (uno por archivo)
.codesearch.db/            # Índice de búsqueda semántica (ignorado)
.search/                   # Caché de búsquedas web (ignorado)
investigacion/            # Artefactos generados por los agentes investigadores (ignorado)
data/                     # Datos auxiliares (ignorado)
scripts/                   # Utilidades auxiliares
```

Todas las definiciones de agentes se encuentran bajo `~/.config/opencode/agents/` localmente, y este README.md sirve como índice y documentación de referencia principal.

## Flujos de trabajo entre agentes

- **Corrección de errores**: `@debug` → `@agente-plan` (modo A) → `@fix` → `@test`
- **Mejoras/Features**: `@agente-plan` (modo B) → `@fix` → `@test`
- **Investigación científica**:
  - Atracción humana → `@Investigador-Cientifico`
  - Otro tema → `@Investigador-Secundario`
- **Operaciones de infraestructura**: `@docker`, `@git`
- **Versionado**: `@git` invoca a `@versionador` para analizar y proponer SemVer; `@git` crea/actualiza el tag local. El usuario decide si hacer `git push` del tag.

## Agentes primarios

| Agente | Archivo | Función |
|--------|---------|----------|
| `@code` | [`code.md`](code.md) | Asistente general de ingeniería de software. Ejecuta tareas, escribe código, sigue convenciones. Breve y directo. |
| `@debug` | [`debug.md`](debug.md) | Investigación estricta de fallos. Solo analiza, no modifica código. Memoria persistente, máximo 3 hipótesis, una a la vez. |
| `@fix` | [`fix.md`](fix.md) | Aplica planes ya aprobados (fixes o features). Modifica código solo dentro del alcance del plan. |
| `@test` | [`test.md`](test.md) | Testing no destructivo. Solo se ejecuta bajo solicitud explícita. Valida fixes ya aplicados. |
| `@agente-plan` | [`agente-plan.md`](agente-plan.md) | Planificación. Modo A: plan de fix desde causa raíz. Modo B: plan de feature/mejora. No modifica código. |
| `@cambio-quirurgico` | [`cambio-quirurgico.md`](cambio-quirurgico.md) | Ejecuta exactamente un cambio puntual declarado. No auto-corrige ni expande scope. Hallazgos fuera de alcance → observaciones. |
| `@frontend-designer` | [`frontend-designer.md`](frontend-designer.md) | Design lead para UI/UX engineering (dashboards, admin panels, apps). Identidad visual deliberada, tokens semánticos, WCAG 2.2 AA, verificación en navegador real. |

## Agentes subagentes

| Agente | Archivo | Función |
|--------|---------|----------|
| `@git` | [`git.md`](git.md) | Operaciones Git. Commits, push, pull, merge, rebase, tags. Mensajes en español sin prefijos. Operaciones de alto riesgo requieren confirmación. |
| `@docker` | [`docker.md`](docker.md) | Docker y Docker Compose. Inspección primero; confirmación reforzada para `down -v`, `prune`, `rm`, `rmi`, etc. |
| `@versionador` | [`versionador.md`](versionador.md) | Propone versión SemVer desde el historial git. Solo inspección; dry-run obligatorio. |
| `@Investigador-Cientifico` | [`Investigador-Cientifico.md`](Investigador-Cientifico.md) | Investigación científica sobre atracción humana (psicología, neurobiología, sociología). Solo fuentes peer-reviewed, académicas `.edu`/`.gov`. |
| `@Investigador-Secundario` | [`Investigador-Secundario.md`](Investigador-Secundario.md) | Investigación científica sobre cualquier otro campo de tema dado. Mismo rigor que `@Investigador-Cientifico`. |

## Permisos y seguridad

Los permisos son específicos por herramienta. Muchos agentes confían en `read/glob/grep` y usan `bash` selectivamente con `ask` para acciones de alto riesgo (por ejemplo, `push --force`, `down -v`, `rm`, `rmi`, `exec --privileged`).

## Skills

Los agentes usan habilidades pre-existentes (`agent-strategies`, `code-search`, `memory-sync`, `token-efficient-workflow`, etc.) en lugar de intentar implementar lógica personalizada. La mezcla de skills se elige según el propósito de cada agente.

| Skill | Agentes que la invocan |
|-------|------------------------|
| `agent-strategies` | `@code` (al inicio de sesión) |
| `commit-msg` | `@git` (al inicio de sesión) |
| `code-search` | `@code`, `@debug` (búsqueda avanzada) |
| `memory-sync` | `@code`, `@debug`, `@fix`, `@test`, `@agente-plan` (memoria persistente) |
| `token-efficient-workflow` | `@code` (orquestación) |
| `postgresqldb` | `@code` (guía PostgreSQL) |
| `ci4-expert` | `@code` (CodeIgniter 4) |
| `interface-design` | `@code`, `@frontend-designer` (dashboards, admin panels) |
| `docx-generator` | `@code` (documentos .docx/.pdf) |
| `erp-e2e-tester` | `@code` (pruebas E2E módulo de compras) |

## Modos

- **primary**: Agente principal — inicia una tarea completa de forma autónoma.
- **subagent**: Agente especializado — realiza subtareas específicas bajo la dirección de un agente principal.

## Uso típico

1. Proporciona un objetivo al repo (por ejemplo, "implementar la autenticación OAuth2").
2. El workflow asigna automáticamente los roles:
   - `@debug` → investiga la superficie del código actual.
   - `@agente-plan` → elabora un plan de feature (Modo B).
   - `@fix` → aplica el plan.
   - `@test` → valida el fix si es requerido.
3. Puedes invocar agentes específicos directamente (por ejemplo, `@git status`, `@docker compose ps`).

## Licencia

Este trabajo está licenciado bajo **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International** (CC BY-NC-SA 4.0).

- ✅ **Compartir** — copiar y redistribuir el material en cualquier medio o formato
- ✅ **Adaptar** — remezclar, transformar y construir a partir del material
- ❌ **Uso comercial** — no está permitido
- ⚠️ **Atribución** — debe dar crédito adecuado
- ⚠️ **CompartirIgual** — las adaptaciones deben distribuirse bajo la misma licencia

Ver el archivo [`LICENSE`](LICENSE) para el texto completo.

## Autor

Agentes desarrollados por los contribuidores del repo.