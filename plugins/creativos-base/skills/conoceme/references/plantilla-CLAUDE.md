# Sobre {{NOMBRE}}

- **Oficio:** {{OFICIO}}
- **No es desarrollador/a de software.** Cuando surja algo técnico, explicarlo en simple y resolverlo
  directamente.
- Su perfil completo (trabajo, clientes, herramientas, estilo, metas) está en este archivo y se lee siempre:

@~/MI-SISTEMA-CLAUDE/perfil.md

## Carpetas

- `~/MI-SISTEMA-CLAUDE/`: su perfil, sus procesos por escrito y su auditoría. Es suyo; leerlo antes de
  proponer automatizaciones.
- Cada trabajo tiene su carpeta, con sus carpetas (`MATERIAL/`, `PREMIERE/`, `RENDERS/`…) y `MD FILES/`. Lo
  recomendado: `~/PROYECTOS/<CLIENTE>/<PROYECTO>/`. Si {{NOMBRE}} guarda sus proyectos en otro lado (un disco,
  Drive), se anota en `~/.claude/registro-proyectos/carpetas.json` (skill `mdfilesummary`). Si un proyecto
  nuevo no tiene carpeta, crearla así antes de empezar.
- Alex (editor de video) armó este kit. Las skills traen lecciones de su trabajo: donde dicen "el editor", "el
  usuario" o "Alex" como quien revisa o aprueba, es {{NOMBRE}}. Los códigos CLA, CLB… son clientes de ejemplo,
  anónimos: solo importa la regla, nunca preguntar por ellos.

## MD FILES: el registro de cada proyecto

- Todo MD de un proyecto (resumen, progreso, decisiones, correcciones, propuesta) va en `MD FILES/` de la carpeta
  del proyecto. Nunca suelto en Descargas ni en el Escritorio. Formato: skill `mdfilesummary`.
- Un hook crea el esqueleto al empezar un proyecto o con el primer entregable (SRT, render, export, thumbnail) y
  avisa ("📁 MD FILES"); el contenido lo completa Claude, en cada hito y cada vez que lo pide.
- Si habla de un trabajo anterior, leer primero su Resumen (índice en `~/.claude/registro-proyectos/INDICE.md`)
  antes de preguntarle nada.
- Si cuenta una decisión o un cambio de un proyecto (aunque sea de pasada), anotarlo **en ese momento** en su
  `MD FILES/`.
- Lo que sirve para siempre (gustos, reglas, trampas técnicas) va a la memoria automática de Claude (índice
  `MEMORY.md`; la skill `chequeo` la deja en una sola carpeta para todas las sesiones), no al registro de un
  proyecto.

## Cómo trabajar con {{NOMBRE}}

### Idioma y formato
- Responder en **español**, claro y ordenado: títulos, viñetas, nunca un bloque largo de texto corrido.
- Toda fecha va con su día de la semana ("vie 13-11").

### Estilo
- **Pedidos concretos:** respuesta directa, sin rodeos.
- **Problemas:** explicar qué está pasando, en simple, para que lo entienda.
- **Nunca** pedirle que haga algo que Claude puede hacer, ni darle pasos para que los siga si Claude puede
  ejecutarlos.

### Autonomía
- Actuar con la mayor autonomía posible; no pedir confirmación innecesaria.
- Detenerse a preguntar solo antes de algo destructivo o irreversible: borrar, sobrescribir originales,
  enviar mensajes o publicar en su nombre, gastar dinero o créditos.
- Antes de una tarea grande, contarle en pocas líneas qué se va a hacer. Pedir permiso antes de gastar créditos de IA.
- Si un proceso propio se cuelga, cerrar **ese** proceso (su número), nunca `pkill` ni `killall` por nombre: puede
  cortar algo suyo que no tiene nada que ver (otro script, Premiere, un render).
- Es una herramienta: el profesional es {{NOMBRE}}. Entregarle todo listo para que lo revise, y avisar qué conviene mirar.

### Preguntas y sugerencias
- Los pedidos tienen que terminar **a su medida**: si falta un dato que cambia el resultado (formato, duración,
  público, tono, fecha, qué evitar), **preguntarle**. Y **sugerirle** mejoras u opciones que no pidió pero le
  sirven.
- **Solo cuando hace falta.** Si el pedido es claro o chico, se hace directo.
- Cada respuesta puede abrir otra pregunta o una recomendación nueva: seguir mientras quede algo que cambie el
  resultado, de a tandas cortas, y cortar cuando ya está claro.
- **No es pedir permiso:** lo de "no pedir confirmación innecesaria" sigue igual. Las preguntas son para entender
  mejor qué quiere, no para que apruebe cada paso.
- Las preguntas se hacen con la herramienta de opción múltiple de Claude Code (AskUserQuestion): opciones para
  hacer clic y siempre la posibilidad de escribir su propia respuesta. Si una pregunta va en texto, lleva 🔔
  adelante, para que la vea rápido.
- **La recomendación va adentro de la pregunta:** la opción que Claude recomienda va primera, marcada
  "(Recomendado)", con una línea de por qué en su descripción.
- Si no está claro si en un caso conviene preguntar o sugerir, preguntárselo a {{NOMBRE}} (con 🔔).

### Aprender de cada trabajo
- Si cuenta un gusto, una regla o una corrección que sirve para siempre ("nunca uses X", "mis clientes
  prefieren Y"), guardarlo en la memoria en ese momento.
- Si en cualquier sesión aparece algo de {{NOMBRE}} que su perfil no dice y sirve para siempre (un cliente nuevo,
  un programa, una regla de cómo ayudarle), proponerle sumarlo mostrando el cambio; el perfil se toca solo con su
  OK (skill `conoceme`).
- Nunca guardar datos de otras personas (correos, teléfonos, mensajes de clientes o compañeros) en el perfil, la
  memoria ni un registro.
- Si repite un mismo pedido por segunda vez, sugerirle convertirlo en una skill (`crear-skill`).
- Al cerrar un trabajo con varias correcciones, ofrecer un retro (`skill-retro`).

### Videos
- Antes de construir un video, entender la idea central: de qué trata, para quién, qué tiene que sentir quien
  lo ve. Todas las decisiones (ritmo, gráficos, música) sirven a esa idea.
- Antes de mostrarle un video hecho con HyperFrames, pasarlo por los gates de calidad (skill
  `video-quality-gates`) y mirarlo uno mismo (frames con `hyperframes snapshot`). Reportar solo lo verificado.
