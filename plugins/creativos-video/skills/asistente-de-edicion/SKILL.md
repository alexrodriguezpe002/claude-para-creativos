---
name: asistente-de-edicion
description: "Mientras la persona graba, le deja el timeline listo para montar: cuando ShotPut Pro (u OffShoot, Hedge, Silverstack o descargar-tarjeta) termina de copiar una tarjeta a la carpeta de destino, sincroniza el audio de la grabadora con los clips por la forma de onda y arma un proyecto XML para Premiere o DaVinci con una carpeta por día, una por cámara y una de audio, y la secuencia del día con todo en orden de grabación (los clips a revisar, marcados). No copia tarjetas ni toca las copias: solo las lee. Corre solo (Mac: launchd; Windows: Programador de tareas), avisa con una notificación y desde el celular se le pregunta «¿ya está el timeline?». Mac y Windows. Usar cuando la persona diga «quiero llegar del rodaje y tener el timeline listo», «que me sincronice mientras grabo», «arma mi asistente de edición», «vigila la carpeta de ShotPut», «cuando termine ShotPut, sincroniza», «¿ya está el timeline?», «arma el timeline ya», «cambia la carpeta del asistente», «apaga el asistente», o cuando copia con ShotPut, OffShoot, Hedge o Silverstack y quiere que el resto sea automático."
---

# Asistente de edición

Scripts: `${CLAUDE_SKILL_DIR}/scripts/asistente.py` (lo que corre) e `${CLAUDE_SKILL_DIR}/scripts/instalar_asistente.py`
(instala, revisa, quita), siempre entre comillas. Motor: el de `sincronizar-audio` (`sincronizar.py`). Corren con el
Python del entorno propio, `<py>` (ver `sincronizar-audio` › Preparar: `numpy pillow imageio-ffmpeg gdown`, la misma línea para todas las skills de video).

Explicarlo en dos líneas: «Tu programa de copia sigue copiando y verificando como siempre. Cuando termina, yo
sincronizo el audio y te dejo el proyecto armado en una carpeta: llegas, lo importas en Premiere y montas.»

## 0. Antes (una vez)
- Entorno propio y autoprueba de `sincronizar-audio`.
- `<py> "<asistente.py>" autoprueba` → tiene que terminar en `✅ Autoprueba OK` (menos de un minuto, en una carpeta
  temporal: simula ShotPut copiando, sellando y una tarjeta más).

## 1. Configurar (con la herramienta de preguntas: opciones + escribir)
- **Carpeta a vigilar:** el destino de ShotPut para este rodaje (la carpeta donde ShotPut crea la de cada tarjeta).
  Si ShotPut copia a dos discos, se vigila **uno solo** (el principal): si no, cada clip aparecería dos veces.
- **Dónde dejar el timeline:** proponer `SINCRO` al lado del proyecto de Premiere, o `<carpeta vigilada> - SINCRO`.
  Nunca dentro de una tarjeta copiada: el asistente frena si la salida cae dentro de una copia sellada.
- **Nombre:** el del proyecto (`SINCRO BODA PEREZ`); cada XML suma el día de grabación.
- Opcional: `--copias` (clips con el audio pegado, para Final Cut o para mandar), `--espera` (minutos sin cambios
  antes de armar; 5) y `--sin-senal` (minutos si el programa de copia no deja ninguna señal; 15).

```
<py> "<asistente.py>" config guardar --carpeta "<destino de ShotPut>" --salida "<carpeta SINCRO>" --nombre "SINCRO <PROYECTO>"
```

**En ShotPut** conviene tener activado (Preferencias › Reportes) un sello (ASC MHL o MHL) o el archivo de sumas, y/o
un reporte «Save with job»: es la señal segura de que la copia terminó. Sin eso, el asistente espera 15 minutos sin
cambios.

## 2. Probar sin instalar
`<py> "<asistente.py>" --una-vez --simular` dice qué ve y qué haría · `--estado` da el resumen.

## 3. Instalar (🔔 pedir OK, diciendo qué se instala y dónde)
```
<py> "<instalar_asistente.py>" instalar
```
- Se copia (con el motor) a `~/MI-SISTEMA-CLAUDE/asistente-edicion/bin/`: la carpeta del plugin cambia con cada
  actualización del kit y el sistema necesita una ruta fija.
- **Mac:** agente `~/Library/LaunchAgents/com.creativos.asistente-edicion.plist`, que revisa cada 2 minutos y cada
  vez que cambia la carpeta vigilada. La primera vez que lee un disco externo (o Documentos, o Escritorio), macOS pide
  permiso para que python acceda: la persona toca **Permitir**. Esas ventanas no salen en las capturas de Claude:
  preguntarle qué ve en la pantalla. Además macOS muestra la notificación «App Background Activity — "python" can
  run in the background»: es el asistente (corre con Python), es normal y no se toca nada. Avisarle antes, para que
  el nombre «python» no lo asuste (probado el jue 19-11-2026).
- **Windows:** tarea «Asistente de edicion» al iniciar sesión, que revisa cada minuto (si Windows no deja crear la
  tarea, queda un acceso oculto en la carpeta Inicio; lo dice el resultado).
- La compu tiene que estar **prendida y despierta** (enchufada; en Mac, sin reposo automático). Mientras sincroniza,
  el asistente no la deja dormir.
- Si graba lejos de esa compu, el material tiene que llegar a la carpeta vigilada: el disco que trae, una carpeta en
  la nube que se sincroniza, o una laptop en el set con el asistente instalado.

## 4. Qué hace
| Situación | Qué hace |
|---|---|
| Está llegando material (ShotPut copiando) | Espera |
| La copia terminó (sello, sumas o reporte nuevo) y la carpeta quedó 5 minutos quieta | Sincroniza y arma el timeline; aviso «✅ Timeline listo · 18 de 20 clips sincronizados…» |
| Terminó, pero el programa no deja ninguna señal | Arma después de 15 minutos sin cambios |
| Llega otra tarjeta | Versión nueva con todo el día (`… _2.xml`); solo analiza lo nuevo |
| No hay audio de grabadora | Arma igual, con el audio de la cámara |
| Disco desconectado | Espera a que vuelva |
| Algo falló | Aviso ❌; no reintenta con el mismo material hasta que llegue algo nuevo o se pida «arma el timeline ya» |

## 5. En Premiere (o DaVinci)
- **Premiere:** Archivo › Importar › el `.xml` más nuevo de la carpeta del timeline. Aparece una carpeta con:
  - la **secuencia del día**, con los clips en orden de grabación (las cámaras mezcladas por hora), cada uno con el
    audio bueno debajo y el de la cámara en sus pistas, apagado;
  - una carpeta por **cámara** (el modelo si el clip lo dice; si no, la carpeta de la tarjeta) y una de **audio**;
  - con varios días, una carpeta por día.
  - Los 🟡 llevan marcador «REVISAR SINCRO» y color amarillo; los ❌, «SIN SINCRO» y rosa; el B-roll sin audio, «SIN
    AUDIO» adelante del nombre.
- Si ya importó una versión anterior y empezó a montar: la nueva trae todo el día; lo que ya editó no cambia.
- **DaVinci Resolve:** Archivo › Importar › Línea de tiempo › el `.xml`.
- Si el XML no abre bien en su programa: `sincronizar.py analizar … --xml-simple` (una secuencia suelta por día, sin
  carpetas, la forma más simple).

## 6. Desde el celular (Remote Control)
- «¿ya está el timeline?» → `<py> "<asistente.py>" --estado` y contestar en dos líneas: cuándo, cuántos clips
  sincronizados y cómo se llama el XML (fechas con el día de la semana).
- «ármalo ya» → `<py> "<asistente.py>" --ahora` (si la carpeta está cambiando, espera a que termine la copia).
- «¿qué clips hay que revisar?» → los 🟡 y ❌ de `informe_sincronizacion.json`, en la carpeta del timeline.

## Mantenerlo
- **Rodaje nuevo:** `config guardar --carpeta … --salida … --nombre …` y después `instalar_asistente.py actualizar`
  (en Mac, para que vigile la carpeta nueva; el estado avisa si quedó vigilando otra).
- **Después de actualizar el kit:** `instalar_asistente.py actualizar`.
- **Quitarlo:** `instalar_asistente.py desinstalar` (con OK). La configuración, el registro y los timelines quedan.
- Registro: `~/MI-SISTEMA-CLAUDE/asistente-edicion/asistente.log` (ahí está la salida completa de cada sincronización).

## Reglas
- **Nunca** mueve, renombra ni borra nada de las copias: se rompería la verificación (el MHL o las sumas de ShotPut).
  El orden va en las carpetas del XML, no en el disco. Por lo mismo, `ordenar-material` no entra en copias selladas.
- No compite con el programa de copia: no copia tarjetas. Si la persona no usa ninguno, `descargar-tarjeta` y
  `vigilante-de-tarjetas` copian y verifican, y el asistente vigila su destino igual.
- No importa nada en Premiere por su cuenta: deja el XML y avisa.

## Probado y sin probar
- **Probado (jue 19-11-2026, Mac):** `autoprueba` con el Python de la Mac: llega una tarjeta a medias (espera), queda
  quieta sin sello (espera la señal), llegan el sello ASC MHL, el MHL al lado de la grabadora, las sumas de ShotPut y
  un reporte (arma a los 5 minutos: 3 de 4 clips sincronizados, las dos cámaras mezcladas por hora y el B-roll
  adentro), las copias quedan intactas, otra tarjeta (versión nueva, solo analiza el clip nuevo) y una carpeta sin
  ninguna señal (arma a los 15 minutos). Instalación en modo simulación (`--simular`).
- **Sin probar:** ShotPut real (dónde deja el reporte y el MHL sale de su manual oficial, Windows 2024.2 y Mac
  2020.2.2; confirmarlo con una copia real), abrir el XML en Premiere y DaVinci reales, la instalación de verdad con
  launchd (el permiso de macOS) y Windows entero (tarea, avisos), material real de varias horas.
