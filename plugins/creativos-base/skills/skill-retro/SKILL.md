---
name: skill-retro
description: "Retro de una sesión de trabajo con una o varias skills: recupera la sesión completa (aunque se haya compactado), encuentra la causa real de cada corrección y propone cambios listos para pegar en cada skill, primero explicados en fácil. Sirve para cualquier skill y cualquier trabajo (video, animación, documentos, oficina). Usar cuando la persona diga \"¿qué aprendiste hoy?\", \"hazme un retro\", \"revisemos qué funcionó y qué no\", \"mejora la skill que usamos\", \"antes de tocar la skill quiero ver todo\", o al cerrar un trabajo con varias rondas de correcciones. No usarla en una sesión sin correcciones ni para un arreglo de una línea. Pedir el retro autoriza solo el informe: nunca edita una skill hasta que la persona elige qué propuestas aplicar, y publicar los cambios (subirlos al kit o a un repo) se pregunta aparte."
---

# Skill retro

Cierra una sesión con un **informe de aprendizajes**, no con una edición directa a la skill. La persona decide
qué se incorpora: esta skill informa y, solo con su elección, aplica.

## Dos modos, dos permisos

1. **Revisión** (lo que se pide con "hazme un retro"): leer, analizar, informar. **No se toca ningún archivo.**
2. **Aplicar**: solo cuando la persona responde con los números de las propuestas que aprueba ("la 1 y la 3",
   "todas"). Se edita eso y nada más.
3. **Publicar** (subir el cambio al kit del equipo, hacer commit o push, abrir una propuesta): **nunca entra en la
   aprobación del paso 2.** Se pregunta aparte, al final, y solo si la skill vive en un repo.

Lo que ya se escribió **durante** la sesión (una regla que la persona dictó y se anotó en el momento) va al
principio del informe, en "Ya cambiado durante la sesión (confirma o lo saco)". No se esconde entre las propuestas.

## Privacidad

- Todo queda en la computadora: el archivo de la sesión se lee local y el resumen se escribe en la carpeta temporal.
- El script tapa claves, contraseñas, tokens, correos y teléfonos. Igual: en el informe se cita lo mínimo
  (una frase corta, no párrafos), y nunca datos de terceros (clientes, correos, nombres de personas ajenas).
- Antes de aplicar un cambio, revisar el texto nuevo buscando datos que no deberían quedar escritos en una skill.

## Paso 1 — Qué skills están en juego, y dónde viven

Nombrarlas al principio del informe. Para cada una, ver **dónde vive** (cambia cómo se aplica):
- **Skill personal** (`~/.claude/skills/<nombre>/`): se edita ahí.
- **Skill del kit** (instalada como plugin, en `~/.claude/plugins/…`): **no se edita la copia instalada** (la
  próxima actualización la pisa). El cambio se lleva al kit con la skill `proponer-mejora`.
- **Skill de otro plugin** (de Anthropic o de terceros): no se toca; si vale la pena, se anota como sugerencia.

Las propuestas van a la capa que corresponde: un gusto o un dato de la persona va a su perfil o a un archivo de
ajustes (nunca dentro del método); un comportamiento, a la skill de proceso; algo medible, a un control automático.

## Paso 2 — Reconstruir la sesión desde el material real

Recuperar la sesión completa, también lo que quedó antes de una compactación y lo que hicieron los subagentes:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/recuperar_sesion.py" --actual
# otra sesión: --buscar "una frase que la persona dijo en esa sesión"  ·  en Windows: py -3 en vez de python3
```

- Si dice que hay **varias sesiones** con esa frase, mostrarle la lista y que elija: **nunca adivinar cuál es**.
- Si no hay archivo (sesión de Cowork o de la web), el retro es **parcial**: se hace con lo que hay en esta
  conversación y el informe lo dice arriba ("Retro parcial: sin el archivo de la sesión").
- Leer el resultado con `grep` o por partes. Si hubo compactación, lo anterior a la marca es lo que Claude ya no
  tenía completo: ahí suelen estar las correcciones olvidadas.

Además de la sesión, las fuentes del trabajo: el diff o los archivos cambiados, la salida de los scripts y
controles, los renders, las capturas que mandó la persona, el `MD FILES/` del proyecto. Si la persona tiene
fuentes propias por tipo de trabajo, están en **`~/.claude/skill-retro/fuentes.md`** (es suyo; si no existe y en
el retro aparece una fuente que siempre conviene mirar, proponer crearlo).

Cada ítem del informe tiene que poder señalarse a algo concreto: una frase de la persona, un archivo, un error.
Nada de "cómo fue la sesión" de memoria. El informe dice qué cubrió ("leí la sesión entera, 2 subagentes, 1
compactación") y qué no pudo leer.

## Paso 3 — Clasificar

- **Funcionó:** se hizo bien a la primera, la persona confirmó sin pedir cambios, o una regla evitó un error conocido.
- **No funcionó:** la persona tuvo que señalar un problema, corrigió una interpretación, algo se le escapó a
  Claude hasta que ella lo vio, o se gastó de más (créditos, tiempo, un reintento evitable).

## Paso 4 — La causa real de cada "no funcionó"

Nombrar la causa, no solo el síntoma:

1. **Hueco:** la skill no decía nada sobre esto.
2. **Ambigüedad:** decía algo que admitía otra lectura, y se tomó la equivocada.
3. **Ejecución:** la regla estaba clara y no se siguió. Se informa, pero **no** se propone otra regla igual.
4. **Preferencia nueva:** información nueva de la persona (un gusto, un umbral, una decisión).

Para cada causa candidata, dos pruebas antes de proponer nada:
- **¿La habría evitado?** Si la regla propuesta hubiera estado escrita, ¿este error no pasaba? Si la respuesta
  es "quizás no", no es la causa.
- **¿Rompe algo que hoy sale bien?** Pensar en un caso de la sesión (o de antes) que funcionó: ¿la regla nueva lo
  empeoraría? Si sí, achicarla.

Y cinco filtros para que algo quede escrito: **se repite** (pasó más de una vez o va a volver a pasar), **depende
de nosotros** (no de un fallo externo de un programa o de internet), **es nuevo** (no está ya escrito en otro
lado), **dura** (no es solo de este caso) y **vale lo que ocupa** (cada línea de una skill se lee en cada uso).

Cada diagnóstico lleva una etiqueta: **Confirmado** (la persona lo dijo o se ve en el material), **Probable**
(hay evidencia, falta confirmar) o **Tentativo** (una hipótesis: va como pregunta).

## Paso 5 — Propuestas

En este orden de preferencia: **corregir** la regla que existe > **juntar** dos reglas en una > **borrar** lo que
contradice > **agregar** algo nuevo. Repetir la misma regla en más lugares no arregla nada.

"Sin cambios" es un resultado válido: muchas sesiones no dejan nada para escribir. Una causa, una propuesta.

Cada propuesta, lista para pegar: archivo y sección, el texto como quedaría (mismo tono y formato, con el caso
concreto entre paréntesis) y su etiqueta. Si la causa era ambigüedad, se reescribe la regla existente, no se
agrega otra que compita.

## Paso 6 — Primero en fácil

El informe tiene dos capas. **Arriba, la versión simple** de cada propuesta: el efecto práctico, sin nombres de
funciones ni medidas como única explicación, con una analogía cuando ayude ("un fundido es como un dimmer; un corte
duro es prender y apagar la luz"). **Abajo, el detalle técnico** para editar la skill.

## Paso 7 — Preguntas abiertas

Lo que no tiene una respuesta objetiva (un umbral, un gusto, dos caminos válidos) va como pregunta, sin
contestarla con una suposición. Si una pregunta tiene opciones, la recomendada va primero, con su porqué en una línea.

## Formato del informe

```markdown
## Qué revisé
<sesión entera / parcial, subagentes, compactaciones, otras fuentes>

## Skills en juego
<nombre — dónde vive: personal / kit / otro plugin>

## Ya cambiado durante la sesión (confirma o lo saco)
- <archivo: qué se escribió y por qué>

## En fácil
1. <efecto práctico + analogía> — Confirmado / Probable / Tentativo
2. …

## Qué funcionó
- <ítem> — <cómo se sabe>

## Qué no funcionó
- <ítem> — causa: <hueco | ambigüedad | ejecución | preferencia nueva>. <evidencia concreta>

## Propuestas (detalle)
1. **<skill/archivo, sección>** — <texto listo para pegar>

## Preguntas para ti
- <pregunta>
```

Cerrar pidiendo qué aplicar: por número, "todas" o "ninguna por ahora".

## Paso 8 — Aplicar solo lo elegido

- Se edita únicamente lo que la persona eligió. **Si aprueba con cambios**, se aplica su versión.
- Antes de darla por aplicada, **comparar el texto aprobado con lo escrito**: si la implementación lo amplía o
  lo generaliza, eso es otra propuesta y se pregunta.
- Releer lo escrito en el archivo (no de memoria). Si se tocó un script: que compile, un caso que tiene que
  pasar y uno que tiene que fallar.
- Si un cambio es para una **skill del kit**, no se edita la copia instalada: se ofrece llevarlo con
  `proponer-mejora`, que pide su propio OK antes de subir nada.
- Si en la misma respuesta la persona trae pedidos nuevos, se separan de la lista aprobada.

## Cuando termines

Confirmar en pocas líneas qué se cambió y dónde, y qué se probó. Borrar el archivo temporal de la sesión
(`retro-<id>.md` en la carpeta temporal). Si quedó algo para publicar, preguntarlo ahora, aparte.
