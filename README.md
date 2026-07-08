---
disable: true
---

# GNR092 — agentesm

*Agentes de IA especializados para OpenCode.*

---

## Descripción

Este repositorio contiene **agentes de IA**, **scripts Python de soporte** y una **base de investigación científica** diseñados para ejecutarse dentro de [OpenCode](https://github.com/opencode-ai), un asistente de código con soporte para agentes personalizados.

Los agentes se definen en archivos `.md` con frontmatter YAML que OpenCode carga automáticamente. Los scripts Python son invocados por los agentes con permisos estrictos (allowlist), manteniendo separación de responsabilidades y seguridad.

Todo el proyecto está en español.

---

## Agentes

| Agente | Archivo | Modo | Descripción |
|--------|---------|------|-------------|
| **Dra. Rebecca v1** | `dra-rebecca.md` | primary | Psicóloga clínica especializada en terapia de pareja e individual. Modalidades: TCC, ACT, DBT, Terapia de Esquemas, Método Gottman, EFT, entre otras. |
| **Dra. Rebecca v2** | `dra-rebecca-v2.md` | primary | Versión 2.3.0 con identidad expandida, 14+ modalidades terapéuticas, banco de técnicas detallado, protocolo de crisis con recursos en 15+ países, sistema de memoria persistente y autenticación por PIN delegada a subagente. |
| **Ciencia de la Atracción** | `ciencia-atraccion.md` | primary | Coach de seducción y relaciones basado en 50+ investigaciones científicas. 20 estrategias, 7 playbooks y sistema de perfil de conquista con memoria persistente. |
| **Pin-Verifier** | `pin-verifier.md` | subagent | Subagente no conversacional que ejecuta `auth_pin.py` y devuelve una línea canónica (`OK` / `ERR_*`). Filtro de autenticación para la Dra. Rebecca v2. |

---

## Scripts

| Script | Propósito | Subcomandos |
|--------|-----------|-------------|
| `scripts/agent_utils.py` | Utilidades deterministas de timestamp y fechas para agentes. Soporta frases relativas en español. | `now`, `now-iso`, `now-unix`, `session-id`, `same-day`, `weekday`, `add-days`, `diff-days`, `relative-date`, `next-weekday`, entre otros. |
| `scripts/auth_pin.py` | Sistema de autenticación por PIN con hash **scrypt** (parámetros OWASP), rate limiting progresivo y almacenamiento seguro (permisos 0600). | `set`, `verify`, `exists`, `delete`, `reset`, `list` |
| `scripts/memory_autorepair.py` | Detecta y repara relaciones faltantes en el grafo de memoria. Entidades creadas sin `create_relations` quedan huérfanas; este script las reconecta. | `plan`, `apply` |
| `scripts/memory_orphan_audit.py` | Auditoría de entidades huérfanas en el grafo de memoria. Heurística conservadora que prefiere falsos positivos sobre falsos negativos. | `audit`, `from-dump` |
| `scripts/memory_retry_queue.py` | Cola persistente de reintentos para operaciones de memoria que fallan (timeout, error de red). Append atómico con `O_APPEND`, lock de fichero y rotación automática a 10 MB. | `enqueue`, `drain`, `peek`, `clear`, `status`, `repair` |

---

## Modelo de seguridad

- **Autenticación por PIN**: Los clientes de la Dra. Rebecca v2 se autentican mediante PIN hasheado con scrypt (N=32768, r=8, p=1). Los hashes y sales nunca se exponen en stdout.
- **Rate limiting progresivo**: 15 minutos base, se duplica por cada intento fallido, tope de 24 horas.
- **Delegación**: El agente primario no ejecuta `auth_pin.py` directamente; delega en el subagente `pin-verifier`, que tiene un alcance mínimo y no es conversacional.
- **Permisos granulares**: Cada agente define una allowlist estricta de comandos `bash` permitidos. El acceso a `edit` está denegado para los agentes de terapia.

---

## Sistema de memoria

Los agentes utilizan un grafo de memoria persistente (`memorialocal`) para mantener contexto entre sesiones. El ecosistema incluye:

- **Entidades y relaciones**: El grafo almacena clientes, sesiones, diagnósticos, técnicas aplicadas y su progreso.
- **Auto-reparación**: `memory_autorepair.py` reconecta entidades huérfanas cuando falla la creación de relaciones.
- **Cola de reintentos**: `memory_retry_queue.py` encola operaciones fallidas y las reintenta con backoff.
- ** Auditoría**: `memory_orphan_audit.py` detecta entidades sin conexión a una raíz declarada.

---

## Base de investigación

El directorio `investigacion/` contiene **50+ fuentes científicas** sobre:

- Neurobiología del amor y el apego (fMRI, hormonas)
- Psicología evolutiva de la selección de pareja
- Feromonas y atracción humana
- Sociología de las relaciones contemporáneas
- Estrategias basadas en evidencia para la seducción y construcción de relaciones

Estas investigaciones son referenciadas directamente por el agente **Ciencia de la Atracción** como respaldo de sus estrategias.

---

## Instalación

```bash
git clone git@github.com:GNR092/agentesm.git ~/.config/opencode/agents
```

Los agentes se cargan automáticamente al iniciar OpenCode desde `~/.config/opencode/agents/`.

### Dependencias

- **Node.js** con `@opencode-ai/plugin` (se instala vía `opencode.json`)
- **Python 3.12+** (scripts de soporte, sin dependencias externas)
- **OpenCode** como cliente

---

## Arquitectura

```
~/.config/opencode/
├── opencode.json                  ← Configuración principal
├── agents/                        ← Este repositorio
│   ├── dra-rebecca.md             ← Agente: Dra. Rebecca v1
│   ├── dra-rebecca-v2.md          ← Agente: Dra. Rebecca v2
│   ├── ciencia-atraccion.md       ← Agente: Ciencia de la Atracción
│   ├── pin-verifier.md            ← Subagente: Pin-Verifier
│   ├── scripts/
│   │   ├── agent_utils.py
│   │   ├── auth_pin.py
│   │   ├── memory_autorepair.py
│   │   ├── memory_orphan_audit.py
│   │   └── memory_retry_queue.py
│   └── investigacion/             ← 50+ fuentes científicas
└── skills/                        ← Skills de OpenCode (no incluidos aquí)
```

---

## Uso

Los agentes se seleccionan en OpenCode según el contexto. Ejemplos de prompts:

**Dra. Rebecca:**
> "Habla con Dra. Rebecca — necesito ayuda con ansiedad en mi relación de pareja"

**Ciencia de la Atracción:**
> "Activa Ciencia de la Atracción — quiero mejorar mi perfil de apps de citas"

**Pin-Verifier** (invocado automáticamente por Dra. Rebecca v2):
> El agente primario solicita la autenticación cuando detecta un cliente nuevo o no verificado.

---

## Contribuir

Las contribuciones son bienvenidas. Por favor:

1. Los mensajes de commit deben estar en español.
2. Los scripts Python deben ser 3.12+ sin dependencias externas.
3. Los agentes deben mantener la estructura de frontmatter YAML y la separación estricta de permisos.

---

## Licencia

MIT
