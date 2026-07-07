# Plan de fix — `pin-verifier-bash-toolset` (contexto multi-despliegue)

**Fecha:** 2026-07-07
**Modo:** Investigación (no aplica cambios al código)
**Estado:** BORRADOR pendiente de aprobación del usuario para delegar a `fix.md`
**Autor:** Agente-investigador (sesión de causa raíz del bug)

---

## TL;DR

El bug original (`pin-verifier` respondía `ERR_NO_BASH_TOOLSET`) **sí existe** pero solo en el fork de opencode usado en Pocophone2 Termux (Hope2333), donde bash no se inyecta a subagentes `mode: subagent`.

En el binario opencode de esta laptop (Linux x86_64), bash **sí** está disponible para subagentes; `pin-verifier` falla por una causa diferente, no documentada en su frontmatter (pendiente investigar en sesión aparte si el usuario lo pide).

Conclusión operativa: **la afirmación "el binario de opencode no inyecta bash en subagentes" es falsa en este despliegue pero verdadera en Pocophone2 Termux**. El plan correcto es (a) sustituir las afirmaciones falsas por contexto y (b) declarar el modelo de seguridad por despliegue.

---

## Hallazgos de la investigación (causa raíz)

### 1. El subagente `pin-verifier` no aporta aislamiento de seguridad en esta laptop

Inspección directa del frontmatter de `dra-rebecca-v2.md` (líneas 13-21):

```yaml
permission:
  bash:
    "python3 ~/.config/opencode/agents/scripts/agent_utils.py *": allow
    "python3 ~/.config/opencode/agents/scripts/auth_pin.py verify *": allow
    "python3 ~/.config/opencode/agents/scripts/auth_pin.py set *": allow
    "*": deny
```

El primario **tiene bash con allowlist para `auth_pin.py verify` y `auth_pin.py set`**. Por tanto:

- Si quisiera leer los hashes scrypt o sales del archivo de PINs, podría hacerlo: tiene `bash` con allowlist, los subcomandos `verify`/`set` ejecutan código en `auth_pin.py`, y ese script tiene acceso de lectura a su propio `data file`.
- La v2.3.0 ("la Dra. Rebecca pierde acceso directo a `auth_pin.py`") es falsa en este despliegue. **Sigue teniendo acceso**.
- `pin-verifier.md` solo añade: una capa de **enmascarado cosmético** (asegura que la salida del primario sea exactamente `OK` o `ERR_*` sin prefijos). Pero `auth_pin.py` ya emite stdout canónico por sí mismo (verificado por inspección de las funciones `verify` y `set`).

**Implicación:** el subagente `pin-verifier` es, en esta laptop, **redundante**. Su invocación añade latencia sin añadir seguridad.

### 2. Donde SÍ funciona el aislamiento es en Pocophone2 Termux

En el fork Hope2333, el binario opencode excluye `bash` del toolset de los subagentes `mode: subagent` aunque el frontmatter declare `tools.bash: true`. En ese entorno:

- `pin-verifier` no puede ejecutar `auth_pin.py` aunque quisiera.
- El primario sí tiene bash con allowlist para `auth_pin.py`.
- Conclusión: en ese entorno, **tampoco hay aislamiento real** entre primario y `auth_pin.py`. La v2.3.0-2.3.1 solo consiguió desplazar el problema.

**Implicación global:** el modelo de seguridad pensado por v2.3.0 (subagente como cámara de aislamiento) **no se cumple en ninguno de los dos despliegues conocidos**. Solo se cumple si el primario NO tuviera bash con allowlist para `auth_pin.py` — pero entonces `auth_pin.py` no se podría invocar en absoluto desde opencode.

### 3. Causa raíz del bug: confusión de modelos de despliegue

La sesión anterior concluyó que la causa raíz era `hipotesis-H1`: "el binario opencode excluye bash en subagentes". Esa hipótesis es **parcialmente correcta** (sí ocurre en Termux) y **parcialmente falsa** (no ocurre en Linux x86_64). El error fue presentarla como universal.

La causa raíz real es:

> **Asumimos que el comportamiento del binario opencode es uniforme entre despliegues, pero no lo es.**

Esto es un caso particular del patrón **deploy-context-multi-host** ya registrado en memoria: una verdad operativa válida en un host se asume válida en todos, y se codifica en frontmatter + protocolo como si fuera invariante.

---

## Cambios recomendados (para que `fix.md` los aplique cuando se apruebe)

### Cambio 1 — `pin-verifier.md` línea 21

**Antes:**
```
El binario de opencode que cargamos **no inyecta `bash` en el toolset de subagentes** `mode: subagent` aunque el frontmatter lo declare (`tools.bash: true` resulta inerte en este binario). Lo confirmamos en `bug-pin-verifier-bash-toolset` (causa raiz `hipotesis-H1`). Solucion adoptada en v2.3.1: el primario ejecuta `auth_pin.py` y tu solo enmascaras su salida.
```

**Después:**
```
El binario opencode de **Pocophone2 Termux (fork Hope2333)** excluye `bash` del toolset de subagentes `mode: subagent` aunque el frontmatter declare `tools.bash: true`. En ese entorno, no puedes ejecutar `auth_pin.py` directamente: el primario lo hace y tu solo enmascaras su salida canónica (`OK` | `ERR_*`).

En **Linux x86_64** (binario oficial opencode), bash **sí** está disponible para subagentes. En ese despliegue tu rol como enmascarador es redundante: el primario podría ejecutar `auth_pin.py` y leer stdout canónico por sí mismo. Aun así, mantén el contrato: enmascara y devuelve una sola línea textual. Si recibes un prompt que no sea de la forma `normalize: <stdout>`, responde `ERR_MISSING_ARG`.

Consulta la nota multi-despliegue en `dra-rebecca-v2.md §23` (próxima v2.3.2) para el modelo de seguridad por host.
```

### Cambio 2 — `pin-verifier.md` línea 25

**Antes:**
```
- **NO** ejecutas `bash` ni ningun subproceso (no tienes `bash` en el toolset).
```

**Después:**
```
- **NO** ejecutas `bash` ni ningun subproceso en Pocophone2 Termux (no tienes `bash` en el toolset por el binario Hope2333). En Linux x86_64 sí podrías, pero el contrato te prohíbe hacerlo: tu salida debe ser estrictamente textual basada en el `stdout` que te pase el primario. Esto preserva la auditoría de quién ejecutó qué.
```

### Cambio 3 — `dra-rebecca-v2.md` líneas 2037-2040

**Antes:**
```
El binario actual de opencode **no inyecta `bash` en el toolset de
subagentes `mode: subagent`** aunque el frontmatter lo declare
(`tools.bash: true`). Esto se confirmó en
`bug-pin-verifier-bash-toolset` (causa raíz `hipotesis-H1`).

Por tanto, el subagente `pin-verifier` se redefine como
**enmascarador puro** (no ejecuta `auth_pin.py` por su cuenta).
Esto preserva la promesa de seguridad de v2.3.0
(la Dra. Rebecca sigue sin acceso directo a la lógica de auth) y
resuelve el bug.
```

**Después:**
```
El comportamiento del binario opencode respecto a `bash` en subagentes
`mode: subagent` **depende del despliegue**:

- **Pocophone2 Termux (fork Hope2333)**: bash **no** se inyecta. El subagente
  `pin-verifier` no puede ejecutar `auth_pin.py`. El primario debe hacerlo y
  pasarle el stdout para enmascarar.
- **Linux x86_64 (binario oficial)**: bash **sí** se inyecta. El subagente
  podría ejecutar `auth_pin.py` por su cuenta, pero el contrato se lo prohíbe:
  el primario sigue siendo quien ejecuta, y el subagente solo enmascara.

Esta sección documenta el flujo para el caso Termux (camino primario + subagente
enmascarador). En el caso Linux x86_64 el subagente es redundante pero se conserva
para tener un único modelo operativo y un único punto de auditoría.

Nota de seguridad: en **ninguno** de los dos despliegues el subagente aísla al
primario de `auth_pin.py`: el primario tiene bash con allowlist para `auth_pin.py
verify *` y `auth_pin.py set *`. El aislamiento real requiere mover `auth_pin.py`
fuera de cualquier ruta accesible por bash (p. ej. a `~/.local/share/` con
permisos `0700` propiedad de un usuario distinto). Tracked como `bug-pin-verifier-
aislamiento-real` (próxima v2.3.3).
```

### Cambio 4 — `dra-rebecca-v2.md` changelog, agregar entrada v2.3.2

Agregar nueva entrada después de v2.3.1:

```
### v2.3.2 (2026-07-07) — Correccion de causa raiz multi-despliegue
- **Fix**: las afirmaciones "el binario opencode no inyecta bash en subagentes"
  en `pin-verifier.md` y `dra-rebecca-v2.md §23.3.1` son ciertas solo para
  Pocophone2 Termux (fork Hope2333). En Linux x86_64 (binario oficial) bash si
  se inyecta. Se corrigen las afirmaciones para indicar el despliegue.
- **Sin cambio de comportamiento**: el flujo operativo (primario ejecuta
  `auth_pin.py`, subagente enmascara stdout) es identico en ambos despliegues.
  En Linux x86_64 el subagente es redundante pero se conserva por uniformidad.
- **Aclaracion de seguridad**: el subagente NO aisla al primario de
  `auth_pin.py` en ninguno de los dos despliegues (el primario tiene bash con
  allowlist `auth_pin.py verify *` y `auth_pin.py set *`). El aislamiento real
  requiere sacar `auth_pin.py` de la ruta accesible por bash. Tracked como
  `bug-pin-verifier-aislamiento-real` para v2.3.3.
- **Compatibilidad**: 100% con v2.3.0 y v2.3.1. Ningun consumidor aguas abajo
  cambia.
- **Agradecimientos**: gracias a la sesion de causa raiz de 2026-07-07 que
  detecto el bug en la afirmacion.
```

### Cambio 5 — Memoria del proyecto (cuando MCP memory acepte payloads)

Marcar `hipotesis-H1-pin-verifier-bash` con observación:
> "VALIDA SOLO PARA POCOPHONE2 TERMUX (fork Hope2333). En Linux x86_64 bash si se inyecta a subagentes. Importancia: cambiar a 'temporal'."

Fusionar `bug-dra-rebecca-no-bash-deployment` en `hipotesis-H1` con observación:
> "Misma causa raiz, distinto nombre. Fusionar."

---

## Tests a ejecutar (cuando `test.md` sea invocado)

1. **Estructural**: `git diff --stat` debe mostrar cambios solo en `pin-verifier.md` (líneas 21, 25) y `dra-rebecca-v2.md` (líneas 2037-2040, 2170-2168 nuevo bloque v2.3.2). Ningún otro archivo debe cambiar.

2. **Funcional del subagente**: invocar `pin-verifier` con `normalize: OK` y verificar que devuelve `OK` textual. Invocar con `hola mundo` (sin prefijo `normalize:`) y verificar que devuelve `ERR_MISSING_ARG`.

3. **Funcional del primario**: ejecutar `bash` con `python3 ~/.config/opencode/agents/scripts/auth_pin.py verify foo bar` desde el primario de Dra. Rebecca y verificar que el allowlist lo permite.

4. **Búsqueda de regresión**: `grep -rn "no inyecta" --include="*.md"` debe devolver 0 coincidencias en el directorio de agentes.

5. **Búsqueda de mención honesta**: `grep -rn "Pocophone2\|Hope2333\|Termux\|multi-despliegue" --include="*.md"` debe devolver al menos 3 coincidencias nuevas (los lugares donde se documenta el contexto).

---

## Lo que este plan NO hace

- **No** elimina el subagente `pin-verifier` en Linux x86_64 (sería overengineering; con un comentario basta).
- **No** cambia el frontmatter de `dra-rebecca-v2.md` (quitar allowlist de `auth_pin.py` rompería la capacidad de invocar `auth_pin.py` en Pocophone2, donde el subagente no tiene bash).
- **No** mueve `auth_pin.py` a `~/.local/share/` con permisos `0700` (eso es v2.3.3, requiere agente-plan.md).
- **No** ejecuta tests (gate del agente `test.md`, no de este plan).
- **No** crea commit (gate del usuario, no del plan).

---

## Riesgos identificados

| Riesgo | Probabilidad | Severidad | Mitigación |
|---|---|---|---|
| El usuario quería solo cambiar la línea 21 de `pin-verifier.md` | Media | Baja | Plan cubre opción A (conservadora); usuario puede pedir variante |
| El MCP memory rechaza payloads grandes y el registro en memoria falla | Alta (ya ocurrió 2×) | Baja | El plan queda en `investigacion/` como artefacto durable; se registrará en memoria cuando MCP lo permita |
| El usuario prefiere v2.3.3 (mover `auth_pin.py` a `~/.local/share/`) antes que v2.3.2 (cosmético) | Baja | Media | Plan lo declara explícitamente como siguiente paso |
| La causa raíz real es más profunda y el plan solo raspa la superficie | Media | Media | El plan documenta esto explícitamente y propone `bug-pin-verifier-aislamiento-real` como follow-up |

---

## Pregunta abierta para el usuario

Antes de invocar `fix.md`, el usuario debe decidir:

**¿Aplica el plan completo (cambios 1-4) o prefiere una variante más conservadora?**

- **Conservadora**: solo cambio 1 + cambio 3 (sustituir las dos afirmaciones falsas más notorias). Sin changelog v2.3.2.
- **Completa (recomendada)**: cambios 1-4 + tests.
- **Agresiva**: además, mover `auth_pin.py` a `~/.local/share/` y dejar solo `agent_utils.py` en el allowlist del primario. Riesgo: rompe Pocophone2 Termux si el binario Hope2333 no soporta esa ruta.

Esperando confirmación.