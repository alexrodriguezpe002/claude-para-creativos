# Feedback del taller de Claude Code

> **Para ti:** arrastra este archivo a Claude Code (o escribe su ruta) y dile: **"haz lo que dice este archivo"**.
> Claude hace solo la revisión, después te hace unas preguntas y al final te muestra el informe antes de
> que se lo mandes a Alex. Tarda unos 15–20 minutos.

---

## Instrucciones para Claude

Esta persona tomó el taller de Claude Code de Alex el **viernes 13-11-2026**. Alex quiere mejorar el taller
para dárselo a otras personas y necesita feedback con datos reales. Haz los 4 pasos en orden, sin pedir
permiso para empezar cada uno.

**Reglas para todo el proceso:**
- **Solo leer.** No cambies, borres, instales ni arregles nada, aunque encuentres algo roto: solo descríbelo.
- **Cuidar el contexto.** Los archivos de sesión pueden ser enormes: no los leas enteros. Usa un script de Python
  que saque solo lo que sirve (mensajes de la persona, errores, comandos, rechazos) y guarda la salida en un
  archivo temporal para leerlo por partes.
- **Privacidad.** En el informe no copies contenido de clientes, correos, datos personales, contraseñas ni claves.
  Describe el tipo de tarea ("un guion para un cliente de autos"), no su contenido.
- Habla en español, simple, sin términos técnicos sin explicar. La persona no es programadora.
- El nombre de la persona está al principio de `~/.claude/CLAUDE.md` ("Sobre <nombre>"). Si no está, pregúntaselo.

### Paso 1 — Revisar lo que hizo

1. **Sesiones de Claude Code desde el 13-11-2026:** son los archivos `.jsonl` dentro de `~/.claude/projects/`.
   Cada subcarpeta es la carpeta donde se abrió la sesión. De cada sesión saca: fecha y hora, carpeta, los
   mensajes de la persona, los errores de las herramientas, los comandos de terminal que se corrieron y las
   acciones que la persona rechazó ("doesn't want to proceed", "rejected", "denied").
2. **Su sistema:** `~/MI-SISTEMA-CLAUDE/` (perfil, procesos, auditoría) y las skills de `~/.claude/skills/`
   creadas o modificadas desde el 13-11-2026. Para saber cuáles son del kit, busca el archivo `skills-v1.txt`
   (`find ~/.claude/plugins ~/kit-claude-creativos -name skills-v1.txt 2>/dev/null`): la primera palabra de cada
   línea es una skill del kit. Las que no están ahí las creó la persona. Si pasó a la versión 2 del kit, sus
   skills viejas del kit están en `~/.claude/skills-anteriores/`.

Busca y anota:
- qué intentó hacer y qué logró;
- dónde se trabó: qué pasaba, cuánto duró (por las horas de los mensajes), si se resolvió y cómo;
- pedidos que repitió o reformuló varias veces;
- momentos en que se rindió o cambió de tema;
- preguntas que muestran que un concepto no quedó claro: sesión, contexto, skill, memoria, permisos, terminal,
  MCP o conectores, instalación, GitHub;
- la lista de **comandos de terminal** que se corrieron, cada uno explicado en una línea simple ("instala un
  programa para transcribir audio");
- la lista de **acciones que rechazó** y qué pedía cada una.

### Paso 2 — Revisar si su sistema quedó bien instalado

Marca cada punto con ✅ o ❌ y una línea de explicación:
- ¿`~/.claude/CLAUDE.md` existe y tiene su nombre? ¿Tiene la memoria única (el bloque `MEMORIA-UNICA` en el
  `CLAUDE.md`, o `autoMemoryDirectory` en `~/.claude/settings.json`)?
- ¿Qué versión del kit tiene? **Versión 2:** `creativos-base` aparece en `~/.claude/plugins/installed_plugins.json`
  o en una carpeta de `~/.claude/plugins/synced/`. **Versión 1:** las skills del kit sueltas en `~/.claude/skills/`
  y los hooks en `~/.claude/settings.json` (`md_files.py`, el sonido al terminar). Si tiene las dos, anótalo: el
  registro y las skills corren repetidos.
- Si tiene la versión 2, corre el script del chequeo, que **solo mira** (busca `chequeo.sh` con
  `find ~/.claude/plugins -name chequeo.sh -path '*creativos-base*' 2>/dev/null` y córrelo con `bash`; en Windows,
  `chequeo.ps1` con PowerShell). Suma sus ✅/❌ a esta lista y no arregles nada de lo que marque.
- **Memoria:** ¿qué carpetas de `~/.claude/projects/` tienen una subcarpeta `memory/` con recuerdos, y cuántos
  tiene cada una? ¿Abrió sesiones en carpetas distintas de su carpeta de usuario?
- ¿Existe `~/.claude/registro-proyectos/INDICE.md`? ¿Hay alguna carpeta `MD FILES/` dentro de `~/PROYECTOS/`?
- ¿Qué conectores o MCP tiene (Google, Higgsfield u otros) y cuáles dieron error en las sesiones?
- ¿Cuántas skills tiene (las suyas en `~/.claude/skills/`, las del kit en los plugins) y cuáles usó de verdad en
  sus sesiones?

### Paso 3 — Entrevistar a la persona

Antes de empezar, dile en 3 o 4 líneas lo más importante que encontraste. Después hazle **una pregunta a la vez**
(máximo 10) y espera su respuesta antes de la siguiente. Puede responder escribiendo o dictando.

- Usa lo que encontraste: "el sábado intentaste X y te salió este error, ¿qué pasó ahí?".
- Pregúntale sí o sí:
  1. qué sintió al dar permisos a Claude, cuál le dio desconfianza y qué le habría dado tranquilidad;
  2. si entendía lo que pasaba cuando había que usar la terminal o algo fallaba, o si solo seguía los pasos;
  3. qué le sorprendió más del taller;
  4. qué partes le sirvieron, cuáles sobraron y qué faltó;
  5. si el problema real que encontraron en el taller para automatizar es el correcto, o si hay otro que le pesa más;
  6. de lo que se instaló (Google, Higgsfield, HyperFrames, la animación), qué fue demasiado para el primer día;
  7. qué le cambiaría al taller antes de recomendárselo a un amigo;
  8. del 1 al 10, qué tan probable es que siga usando Claude Code, y qué haría falta para que sea un 10.
- Si responde algo vago ("estuvo bien", "todo bien"), repregunta hasta tener un ejemplo concreto.

### Paso 4 — Escribir el informe

Guárdalo en `~/Desktop/feedback-taller-<nombre>.md` con estas secciones:

1. **Resumen** en 5 líneas
2. **Qué hice con Claude Code desde el taller** (hechos, con fechas)
3. **Dónde me trabé:** qué pasaba, cuánto tiempo, si se resolvió y cómo
4. **Permisos y terminal:** la lista de comandos explicados, las acciones rechazadas y cuáles me dieron desconfianza
5. **Estado de mi instalación:** la lista del Paso 2
6. **Conceptos:** cuáles entendí y cuáles me confunden, con la evidencia de mis sesiones
7. **Qué funcionó del taller**
8. **Qué cambiaría, cortaría o agregaría**
9. **Lo que quiero lograr ahora con Claude**
10. **Nota del 1 al 10** y qué haría que sea un 10

Al terminar, muéstrale el informe completo y pregúntale si quiere cambiar o quitar algo. Cuando lo apruebe,
dile que se lo mande a Alex por WhatsApp o correo (el archivo está en su Escritorio).
