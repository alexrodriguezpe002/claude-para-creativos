---
name: descargar-tarjeta
description: "Copia una tarjeta de cámara (o un SSD de rodaje) a 2 o más discos con verificación real: lee la tarjeta una vez, escribe en todos los discos a la vez, vuelve a leer cada copia desde su disco y compara las huellas (MD5). Deja en cada copia un manifiesto .mhl (el que leen Hedge, OffShoot, ShotPut y Silverstack) y un informe con clips, duración y códec. Nunca borra ni formatea la tarjeta, nunca pisa archivos y, si se corta, sigue desde donde quedó. Mac y Windows. Usar cuando la persona diga «descarga la tarjeta», «respalda la tarjeta», «copia el material del rodaje», «haz el backup de la tarjeta», «vacía la tarjeta» (copiarla, no borrarla), «offload», «pasa la tarjeta a los discos», o conecte una tarjeta de cámara pidiendo guardarla. No es «respaldar» (ese respalda el sistema de Claude en GitHub)."
---

# Descargar tarjeta

Motor: `${CLAUDE_SKILL_DIR}/scripts/descarga.py` (solo Python, nada que instalar; siempre entre comillas).
En Mac se corre con `python3`; en Windows, con `py`. Abajo dice `python3 "<motor>"`.

La primera vez, decirle a la persona en una línea: «La tarjeta solo se lee. Cada copia se vuelve a leer desde su
disco y se compara con la tarjeta. Recién con el ✅ de las dos copias se formatea, y en la cámara.»

## 1. Ver qué hay conectado

```
python3 "<motor>" detectar
```

🎞️ = tarjetas de cámara (dice de qué cámara: Sony, Canon, P2, RED, Blackmagic, DCIM de celular, dron o GoPro, audio).
💽 = discos, con su espacio libre. `python3 "<motor>" config mostrar` dice lo que se guardó la vez anterior
(proyecto, discos, plantilla de carpetas).

## 2. Preguntar lo que falta (una sola vez, con la herramienta de preguntas: opciones + escribir la suya)

- **Qué tarjeta**, si hay más de una.
- **A qué discos**: dos discos distintos (Recomendado). Ofrecer primero los que ya guardó.
- **Proyecto**: el de la última vez o uno nuevo.
- **Nombre de la tarjeta**: el del volumen (A001, B002…). Si el volumen tiene un nombre genérico ("Untitled",
  "NO NAME", "EOS_DIGITAL"), el motor la numera sola (SONY_01, SONY_02…) o la persona da el de su rollo.

Con todo guardado, la única pregunta es: «¿Copio A001 a RESPALDO1 y RESPALDO2 (proyecto NIKE)?».

## 3. Plan (no copia nada)

```
python3 "<motor>" plan --origen "<tarjeta>" --destino "<disco 1>/<carpeta>" --destino "<disco 2>/<carpeta>" --proyecto "<proyecto>" [--tarjeta A001]
```

Muestra dónde queda cada copia (`<carpeta>/<PROYECTO>/<AAAA-MM-DD>/<TARJETA>`, con la fecha del día en que se
grabaron los clips), cuánto pesa, cuánto espacio hay y los avisos. Si hay ❌ (no entra, un disco no está conectado,
las dos copias caerían en el mismo disco), explicarlo en simple y resolverlo antes de copiar.
Otra estructura de carpetas: `--plantilla "{proyecto}/{dia}/{tarjeta}" --dia DIA_01` (tiene que llevar `{tarjeta}`,
así dos tarjetas nunca se mezclan).

## 4. Copiar

El mismo comando con `copiar` en lugar de `plan`. Si pesa más de unos 2 GB, correrlo en segundo plano y avisar
al terminar. Cada 5 s escribe una línea: archivo, etapa (copiando o verificando), MB/s, porcentaje y cuánto falta.
La compu no se duerme mientras copia.

Al terminar:
- **✅ «Ya se puede formatear la tarjeta EN LA CÁMARA»** → decirlo tal cual.
- **❌ «NO formatees la tarjeta: …»** → explicar el motivo con la tabla de abajo.

Lo que queda en cada copia: el manifiesto `<TARJETA>_<fecha>.mhl` en la raíz de la carpeta de la tarjeta, y en
`_DESCARGA/` el informe (`informe_<fecha>.html`, para ver o imprimir a PDF; abrirlo con `open` en Mac o `start` en
Windows), el CSV para Excel y el estado de la copia.

## 5. Ofrecer (una vez, sin insistir)

- Guardar discos y proyecto para la próxima: `python3 "<motor>" config guardar --proyecto "<P>" --destino "<d1>" --destino "<d2>"`.
- El vigilante (skill `vigilante-de-tarjetas`): que avise o copie solo cuando se conecta una tarjeta.

## Si algo sale mal (código de salida)

| Código | Qué pasó | Qué hacer |
|---|---|---|
| 2 | No empezó: no entra, un disco no está conectado o las dos copias caerían en el mismo disco | Liberar espacio, conectar el disco o elegir otro. Nada se copió. |
| 3 | Se cortó la lectura de la tarjeta (la sacaron, falló el lector o el cable) | Reconectar y correr **el mismo comando**: sigue desde donde quedó. Si se repite, probar otro lector. |
| 4 | Se llenó o falló un disco de destino | Liberar espacio o cambiar disco o cable, y correr el mismo comando. |
| 5 | Una copia no coincide con la tarjeta, o en el destino ya había un archivo con ese nombre y otro contenido (no se pisó) | Archivo distinto: con el OK de la persona, repetir con `--apartar-conflictos` (lo renombra a `.DISTINTO_<fecha>` y copia el de la tarjeta). Copia que no verifica dos veces: ese disco o su cable fallan; usar otro. |
| 130 | Se detuvo (Ctrl+C o se apagó la compu) | El mismo comando sigue. |

## Reglas

- Nunca formatear ni borrar la tarjeta desde la computadora: se formatea en la cámara, después del ✅.
- Dos discos físicos distintos. El motor no deja poner las dos copias en el mismo disco
  (`--permitir-mismo-disco` solo si la persona lo pide sabiendo el riesgo).
- No sacar la tarjeta ni los discos mientras copia. Al terminar, expulsar los discos (no tirar del cable).
- No editar desde la tarjeta: se edita desde una de las copias.
- Los `.<archivo>.parcial-descarga` son copias a medias del propio motor: se borran solos al seguir.
- Huella MD5 por defecto (la leen todos los programas de DIT); `--algoritmo sha1` si la producción la pide.
- Primera vez en una computadora: `python3 "<motor>" autoprueba` (10 s, en carpetas temporales) confirma que todo
  anda y dice si la relectura sale del disco («sin caché») o de la memoria.
- Por qué funciona así (huellas, relectura, manifiestos): `references/como-funciona.md`.
