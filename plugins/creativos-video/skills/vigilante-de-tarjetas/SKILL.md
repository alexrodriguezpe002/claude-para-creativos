---
name: vigilante-de-tarjetas
description: "Instala, con permiso, un vigilante que al conectar una tarjeta de cámara avisa y ofrece copiarla a los discos guardados, con verificación (o la copia sola, si la persona lo elige), y al terminar avisa si ya se puede formatear. Mac (launchd: se activa al conectar un disco) y Windows (Programador de tareas). También lo revisa, cambia de proyecto, actualiza o quita. Usar cuando la persona diga «quiero que se respalde solo al meter la tarjeta», «arma el vigilante», «que me avise cuando conecte una tarjeta», «copia automática de tarjetas», «cambia el proyecto del vigilante», «¿está andando el vigilante?», «apaga o quita el vigilante», o cuando se le ofrece después de una descarga con descargar-tarjeta."
---

# Vigilante de tarjetas

Scripts: `${CLAUDE_SKILL_DIR}/scripts/instalar_vigilante.py` (instala, revisa, quita) y
`${CLAUDE_SKILL_DIR}/scripts/vigilante.py` (lo que corre). Motor de copia: el de `descargar-tarjeta`.
Mac: `python3` · Windows: `py`.

**Si la persona ya copia con ShotPut Pro, OffShoot, Hedge o Silverstack, no instalar este vigilante:** los dos
querrían la misma tarjeta. Que siga con su programa y usar `asistente-de-edicion`, que espera a que su programa
termine y le deja el timeline listo.

Explicarlo en dos líneas: «Cuando conectes una tarjeta, te pregunta si la copia a tus dos discos y verifica las
copias (o la copia sola). Corre aunque Claude esté cerrado, nunca borra nada y, si no contestas en 10 minutos, no
copia.»

## 1. Ver cómo está

```
python3 "${CLAUDE_SKILL_DIR}/scripts/instalar_vigilante.py" estado
python3 "${CLAUDE_SKILL_DIR}/scripts/vigilante.py" --estado
```

El primero dice si está instalado y si su versión es la del kit; el segundo, qué tarjetas ve y qué haría con cada una.

## 2. Configurar (una vez, con la herramienta de preguntas: opciones + escribir)

- **Discos de destino** (dos distintos) y **proyecto actual**:
  `python3 "${CLAUDE_PLUGIN_ROOT}/skills/descargar-tarjeta/scripts/descarga.py" config guardar --proyecto "<P>" --destino "<d1>" --destino "<d2>"`
- **Modo**: «Preguntar antes de copiar (Recomendado)» o «Copiar solo, sin preguntar» → `--modo-vigilante preguntar|automatico`.
- **Qué tarjetas**: todas las de cámara (Recomendado) o solo algunas (`--vigilar sony-xavc sony-xdcam canon-xf p2 dcim …`).
- **Discos que no debe tocar** (por ejemplo un SSD de trabajo que tiene una carpeta DCIM): `--ignorar <NOMBRE> …`.

## 3. Probar sin instalar

Con una tarjeta conectada: `python3 "${CLAUDE_SKILL_DIR}/scripts/vigilante.py" --una-vez --simular` muestra qué
haría, sin avisos ni copias.

## 4. Instalar (🔔 pedir OK, diciendo qué se instala y dónde)

```
python3 "${CLAUDE_SKILL_DIR}/scripts/instalar_vigilante.py" instalar
```

- El vigilante y su motor se copian a `~/MI-SISTEMA-CLAUDE/respaldo-material/bin/`: la carpeta del plugin cambia
  con cada actualización del kit y el sistema necesita una ruta fija para lanzarlo.
- **Mac:** queda un agente en `~/Library/LaunchAgents/com.creativos.vigilante-tarjetas.plist` que se activa cada
  vez que se conecta un disco. La primera vez que lee una tarjeta, macOS pide permiso para que python3 acceda a
  «volúmenes extraíbles»: la persona toca **Permitir**. Esas ventanas no salen en las capturas de Claude:
  preguntarle qué ve en la pantalla.
- **Windows:** tarea «Vigilante de tarjetas» al iniciar sesión, que revisa cada 5 s. Si Windows no deja crear la
  tarea sin administrador, queda un acceso oculto en la carpeta Inicio (lo dice el resultado).

## 5. Probar con la persona

Conectar una tarjeta: aparece la pregunta (Mac: «Ahora no» / «Copiar»; Windows: Sí / No). Al terminar llega el
aviso ✅ («ya se puede formatear en la cámara») con la opción de abrir el informe, o ❌ con el motivo.

## Qué hace con cada tarjeta

| Situación | Qué hace |
|---|---|
| Tarjeta nueva | Pregunta (o copia sola, en modo automático) |
| La cámara grabó más desde la última copia | Ofrece copiar solo lo nuevo |
| Ya está copiada y verificada | Avisa que se puede formatear (una vez cada 6 h) |
| Dijeron «Ahora no» o no contestaron | No vuelve a preguntar por esa tarjeta en 12 h |
| Falta conectar un disco de destino | Avisa cuál conectar; no copia a uno solo |
| Es un disco de destino o está en «ignorar» | No la toca |

## Mantenerlo

- **Rodaje nuevo:** `descarga.py config guardar --proyecto "<nuevo>"` (no hace falta reinstalar).
- **Después de actualizar el kit:** `instalar_vigilante.py actualizar` (el estado avisa si quedó viejo).
- **Quitarlo:** `instalar_vigilante.py desinstalar` (con OK). La configuración y el historial quedan.
- Registro: `~/MI-SISTEMA-CLAUDE/respaldo-material/vigilante.log`. Ante un ❌, leerlo y explicarle a la persona
  qué pasó con la tabla de errores de `descargar-tarjeta`.
