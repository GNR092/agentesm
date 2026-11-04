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

- **Enrutamiento global**: `@orquestador` (agente predeterminado en `~/.config/opencode/opencode.json`) selecciona un agente según la petición y las señales del proyecto. La selección explícita del usuario tiene prioridad.
- **Corrección de errores**: `@01-debug` → `@02-agente-plan` → `@03-fix`; `@04-test` solo ante solicitud explícita.
- **Mejoras/Features**: `@02-agente-plan` → `@03-fix` según aprobación y alcance del plan.
- **Investigación científica**:
  - Atracción humana → `@Investigador-Cientifico`
  - Otro tema → `@Investigador-Secundario`
- **Operaciones de infraestructura**: `@docker-expert` (diseño, diagnóstico y revisión) → `@docker` (ejecución); `@git`
- **Versionado**: `@git` invoca a `@versionador` para analizar y proponer SemVer; `@git` crea/actualiza el tag local. El usuario decide si hacer `git push` del tag.

## Agentes principales

| Agente | Archivo | Función |
|--------|---------|----------|
| `@orquestador` | [`orquestador.md`](orquestador.md) | Agente predeterminado global. Detecta el dominio y delega a agentes existentes; pregunta si hay ambigüedad. |
| `@code` | [`code.md`](code.md) | Ingeniería de software general; fallback para stacks sin especialista. |
| `@01-debug` | [`01-debug.md`](01-debug.md) | Diagnóstico de fallos sin modificar código. |
| `@Agente-Debugger` | [`Agente-Debugger.md`](Agente-Debugger.md) | Acompañamiento socrático para depuración. |
| `@02-agente-plan` | [`02-agente-plan.md`](02-agente-plan.md) | Planificación de fixes y features; no modifica código. |
| `@03-fix` | [`03-fix.md`](03-fix.md) | Aplica planes aprobados dentro de su alcance. |
| `@04-test` | [`04-test.md`](04-test.md) | Pruebas no destructivas, solo ante solicitud explícita. |
| `@cambio-quirurgico` | [`cambio-quirurgico.md`](cambio-quirurgico.md) | Ejecuta un cambio puntual sin ampliar el alcance. |
| `@django-expert` | [`django-expert.md`](django-expert.md) | Desarrollo y diagnóstico especializado en Django. |
| `@frontend-designer` | [`frontend-designer.md`](frontend-designer.md) | UI/UX engineering y accesibilidad para interfaces de producto. |
| `@linux-expert` | [`linux-expert.md`](linux-expert.md) | Investigación, depuración y cambios de sistemas Linux. |
| `@docker-expert` | [`docker-expert.md`](docker-expert.md) | Diseño, diagnóstico y revisión de Docker/Compose; delega operaciones a `@docker`. |
| `@ciberseguridad` | [`ciberseguridad.md`](ciberseguridad.md) | Seguridad de APIs, servidores, arquitectura y DevSecOps. |
| `@minecraft` | [`minecraft.md`](minecraft.md) | Diagnóstico de Minecraft Java, mods y perfiles. |

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
| `code-search` | `@code`, `@01-debug` (búsqueda avanzada) |
| `memory-sync` | `@code`, `@01-debug`, `@03-fix`, `@04-test`, `@02-agente-plan` (memoria persistente) |
| `token-efficient-workflow` | `@code` (orquestación) |
| `postgresqldb` | `@code` (guía PostgreSQL) |
| `ci4-expert` | `@code` (CodeIgniter 4) |
| `interface-design` | `@code`, `@frontend-designer` (dashboards, admin panels) |
| `docx-generator` | `@code` (documentos .docx/.pdf) |
| `erp-e2e-tester` | `@code` (pruebas E2E módulo de compras) |

## Modos

- **primary**: Agente principal de una sesión.
- **subagent**: Solo se invoca desde otro agente.
- **all**: Puede usarse directamente o como subagente. El orquestador usa este modo para delegar a los agentes principales existentes sin duplicarlos.

## Uso típico

1. Proporciona un objetivo al repo (por ejemplo, "implementar la autenticación OAuth2").
2. `@orquestador` inspecciona las señales mínimas del proyecto y delega según la petición.
3. En tareas de código general, puede usar el flujo correspondiente: diagnóstico → plan → ejecución aprobada; pruebas únicamente si se solicitan.
4. Puedes invocar agentes específicos directamente (por ejemplo, `@git`, `@docker`).

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
