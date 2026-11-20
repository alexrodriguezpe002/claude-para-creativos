---
name: crear-skill
description: Convierte un proceso de trabajo en una skill propia de Claude Code, en español — entrevista lo que falta, escribe el SKILL.md (y un script si hace falta), la prueba con un caso real, la corrige y la deja instalada. Usar cuando la persona diga "hagamos una skill para…", "quiero automatizar esto", "convierte esto en una skill", "cada vez que te pido X hazlo así", después de una auditoría de procesos, o cuando repite el mismo pedido por segunda vez.
---

# Crear una skill

Una skill es una **receta escrita** que Claude lee cuando el pedido coincide con su descripción: los pasos, las
reglas, los ejemplos y, si hace falta, un script. Las skills propias viven en `~/.claude/skills/<nombre>/SKILL.md`
(las del kit vienen en los plugins `creativos-…` y no se editan ahí: se mejoran con `proponer-mejora`).

Explicárselo así la primera vez, en dos líneas. Y que lo vea: abrir la carpeta de la skill al terminar.

## 1. Entender el proceso
- Si viene de la auditoría, leer su ficha en `~/MI-SISTEMA-CLAUDE/auditoria/`.
- Si no, preguntar (🔔, de a 3) lo mínimo: con qué empieza, qué entrega, los pasos, qué revisa para saber que
  quedó bien, qué le corrigen siempre.
- **Pedirle un ejemplo real** (un brief, un archivo, una entrega anterior buena). Sin ejemplo, la skill sale
  genérica.

## 2. Decidir la forma
- **Solo instrucciones** (textos, guiones, mails, análisis): SKILL.md con pasos, reglas y un ejemplo bueno.
- **Instrucciones + script** (archivos: renombrar, convertir, ordenar, medir): un script en `scripts/` que
  haga lo mecánico; el SKILL.md dice cuándo y cómo correrlo.
- **Datos fijos** (paleta de un cliente, tarifas, plantillas): en `references/`, para no repetirlos nunca más.
- **Datos de la persona o del equipo, aparte del método.** Lo que cambia de persona a persona (sus clientes, sus
  carpetas, su firma, sus tarifas) va en un archivo de ajustes (`references/ajustes.md` o en su perfil), no
  mezclado en los pasos. Así la skill se puede compartir sin datos y cada uno completa lo suyo.

## 3. Escribir el SKILL.md
```
---
name: <nombre-corto-con-guiones>
description: <Qué hace + cuándo usarla, con las frases que diría la persona. Esto decide si Claude la usa:
  que sea específica y con 4 o 5 maneras de pedirla.>
---
# <Título>
## Antes de empezar   (qué leer, qué preguntar si falta)
## Pasos              (numerados, concretos)
## Reglas             (las de la persona, en sus palabras)
## Cómo saber que quedó bien   (lo que se revisa antes de entregar)
## Ejemplo            (uno real, corto)
```
- Escrita para Claude, en español, clara. Nada de relleno: cada línea cambia el resultado.
- Lo que siempre se pregunta, que se pregunte con opciones: la recomendada primero, con una línea de por qué.
- **Un freno antes de lo que no tiene vuelta atrás o sale afuera** (borrar, sobrescribir, enviar, publicar, pagar,
  gastar créditos): la skill lo dice con todas las letras y pide OK en ese paso.
- Si la skill entrega un informe, primero la versión en fácil (qué cambia para la persona) y después el detalle.

## 4. Probarla de verdad
- Pedirle que **cierre y vuelva a abrir** Claude (o abrir una sesión nueva) y que la pida con sus palabras.
- Correrla con el ejemplo real. Mostrarle el resultado y preguntar (🔔) qué cambiaría.
- Corregir la skill (no solo el resultado) y volver a probar. Dos o tres vueltas suelen alcanzar.

## 5. Dejarla en orden
- Confirmar que está en `~/.claude/skills/<nombre>/`.
- Agregar una línea en `~/MI-SISTEMA-CLAUDE/mis-skills.md`: nombre, qué hace, cómo se pide, fecha.
- Si le sirve a su equipo, ofrecer llevarla al kit con `proponer-mejora` (sin datos de clientes ni de la persona:
  esos quedan en su archivo de ajustes).

## Lecciones que ya pasaron
- **Construir con el modelo más capaz.** Una skill se escribe o se cambia con el modelo más capaz que tenga la
  persona; uno más barato sirve para ejecutarla o para tareas mecánicas (copiar, medir, renderizar). Si un modelo
  barato tocó una skill, el capaz la revisa antes de usarla: con modelos flojos quedan errores que aparecen después.
- **Decir qué cubre una automatización.** Al terminarla o cambiarla, una línea con lo que cubre y otra con lo que
  no ("solo actúa en la primera importación de cada proyecto"). Si no sabe el límite, lo descubre cuando falla y
  cree que se rompió.
- **Un control nunca aprueba sin datos.** Todo script que revisa algo imprime cuánto leyó ("17 cortes, 0 de
  escena"); si no leyó nada, falla con un código distinto de 0 en vez de decir que todo está bien.
