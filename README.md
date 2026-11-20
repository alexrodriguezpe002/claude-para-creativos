# Kit de Claude para creativos

Un punto de partida para usar **Claude** (la app de escritorio: Cowork y Code) en publicidad y video: que Claude te
conozca desde el día uno, que encuentre contigo qué parte de tu trabajo se puede automatizar y que te ayude a crear
tus propias skills.

Lo armó Alex (editor de video) con lo que le funcionó en su propio trabajo. Desde la versión 2 viene como
**plugins**: se instala desde la app y las mejoras te llegan solas.

## Instalar (una sola vez)

1. En la app de Claude (puede estar en inglés): **Customize › Plugins › + Add › Add marketplace** (en español:
   Personalizar › Plugins › Agregar). En **URL** escribe `alexrodriguezpe002/claude-para-creativos`, o la ruta de la carpeta del kit
   si te la pasaron en un disco o un ZIP, y toca **Sync**. Escribir `/plugin` en una conversación de Code abre la
   misma pantalla.
   - El repositorio es público: no pide cuenta de GitHub ni ningún código. Si dice «This marketplace could not be
     accessed… enter a personal access token», la URL quedó mal escrita: revísala. No hace falta crear ningún token.
2. Cierra la app por completo y vuelve a abrirla. La app puede instalar los 4 plugins: el chequeo deja los tuyos.
3. Abre la pestaña **Code** en tu carpeta de usuario y escribe: **"haz el chequeo"**. Claude revisa qué le falta a
   tu computadora, te pregunta qué haces para dejar solo los plugins de tu trabajo y arregla lo demás contigo, con
   tu permiso.
4. Escribe **"conóceme"** y pega lo que exportaste de ChatGPT: queda tu perfil.

Los nombres de los botones pueden cambiar con la versión de la app. Si algo no aparece, `INSTALAR.md` tiene otros
caminos (la pestaña Code o la terminal), y en una Mac también sirve `zsh instalar.sh`.

**¿Ya tenías la versión 1** (la que se instalaba con `instalar.sh`)? Dile a Claude **"actualiza el kit"**: pasa todo
a la versión 2 sin perder nada. Tu `CLAUDE.md`, tu perfil y tu memoria quedan como estaban; las skills viejas se
guardan en `~/.claude/skills-anteriores/`.

## Qué trae

| Plugin | Para quién | Skills |
|---|---|---|
| `creativos-base` | Todos | `chequeo`, `conoceme`, `preguntame`, `crear-skill`, `skill-retro`, `mdfilesummary` (el registro de cada proyecto), `proponer-mejora`, `revisar-propuestas`, `actualizar-kit`, `conectar-celular`, `respaldar` (respaldo diario a tu GitHub privado), `ficha-de-equipo` (tu ficha de quién es quién en el repo de tu equipo) y `mac-cleanup` (solo Mac) |
| `creativos-video` | Editores | `transcribir`, `video-a-premiere`, `ordenar-material`, `brief-a-guion`, `clean-audio-cuts`, `podcast-audio-clean`, `music-bed`, `subtitle-audit`, `higgsfield-imagen-video`, `higgsfield-a-premiere`, el respaldo del material de cámara: `descargar-tarjeta`, `verificar-material`, `vigilante-de-tarjetas`; `sincronizar-audio` (audio de la grabadora con los clips), `asistente-de-edicion` (cuando termina la copia de ShotPut u otro programa, deja el timeline del día listo para Premiere) y `versiones-para-redes` (9:16, 1:1, 4:5, 16:9 y WhatsApp) |
| `creativos-animacion` | Quien anima con código (opcional) | HyperFrames y sus partes, captions (`caption-creator`, `clean-captions`, `embedded-captions`, `podcast-captions`), `motion-graphics`, `grafica-dato`, `video-quality-gates` y más (27) |
| `creativos-oficina` | Procesos y oficina | `auditoria-procesos` |

Se piden hablando: "haz el chequeo", "conóceme", "auditemos mis procesos", "hagamos una skill para…",
"transcribe este video", "baja este video y ármame el proyecto de Premiere", "hagamos un retro".

El plugin base trae también automatismos: el **registro de proyectos** (cada trabajo con su carpeta `MD FILES/`, que
Claude completa y lee al retomarlo), el **respaldo diario** a tu GitHub privado y un **sonido** cuando Claude termina
(en Mac; se apaga creando el archivo `~/.claude/sin-sonido`). Corren en la pestaña **Code**; en Cowork no (ahí el
registro se pide: "actualiza el registro del proyecto").

Cada skill trae adentro las lecciones del trabajo de Alex que le sirven. Donde dicen "el editor" o "el usuario" como
quien revisa o aprueba, eres tú. Los códigos CLA, CLB… son clientes de ejemplo, anónimos: solo importa la regla.

## Tu información es tuya

Tu perfil (`~/MI-SISTEMA-CLAUDE/`), tu memoria, tus skills propias y tus proyectos quedan **solo en tu computadora**.
Este repositorio tiene solo herramientas: nunca datos personales ni de clientes.
La única excepción es en el repo de un **equipo** (una empresa con su propio kit): tu **ficha de equipo**
(`ficha-de-equipo`: cómo te dicen, tu rol, de qué te encargas y qué te pueden pedir, sin nada personal), para que el
Claude de todos sepa quién es quién. La ves y la apruebas antes de que suba, y la aprueba quien mantiene el equipo. Las skills hechas para una sola
persona van en el repo privado de su equipo (`a-medida/`): las instala `actualizar-kit` y nunca van dentro de los
plugins.

## Actualizar y mejorar

- **Actualizar:** dile a Claude **"actualiza el kit"**: trae lo nuevo y te cuenta qué cambió.
- **Proponer una mejora:** "propón esta mejora" (`proponer-mejora`): Claude prepara el cambio, te lo muestra y lo
  envía como propuesta. No tocas GitHub.
- **Quien mantiene el kit:** "¿qué propuestas hay?" (`revisar-propuestas`): resumen de cada una, prueba y, con tu OK,
  la une. También deshace una unión.

## Windows

El plugin base está preparado para Windows (el chequeo tiene su versión de PowerShell y los hooks corren con Git
Bash), pero todavía no se probó en una PC. `mac-cleanup` es solo de Mac; `conectar-celular` ya trae la versión de Windows, sin probar todavía. Las skills de video
pesadas se irán marcando a medida que se prueben.

## Para quien facilita

`GUIA-SESION.md`: cómo llevar la sesión de implementación (agenda, instalación, problemas comunes, seguimiento).

## Créditos

Varias skills de `creativos-animacion` parten de las de [HyperFrames](https://github.com/heygen-com/hyperframes)
(HeyGen, licencia Apache 2.0) y `talking-head-recut` parte de [vtake-skills](https://github.com/notedit/vtake-skills)
(MIT). El detalle de cada componente de terceros y sus licencias está en `AVISOS-DE-TERCEROS.md`.
