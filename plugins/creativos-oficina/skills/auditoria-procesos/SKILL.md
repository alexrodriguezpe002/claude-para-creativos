---
name: auditoria-procesos
description: Auditoría personalizada de los procesos de trabajo de una persona de publicidad o video — lee lo que escribió (tareas que repite o quiere delegar), la entrevista proceso por proceso para completar lo que falta, puntúa cada uno por tiempo ahorrado y facilidad, y entrega un informe con qué automatizar primero, qué skill crear para cada uno y un plan de 2 semanas. Usar cuando diga "auditemos mis procesos", "qué puedo automatizar", "tengo mis procesos por escrito", "qué le puedo delegar a Claude", "ayúdame a ver qué optimizar", o pase una lista de tareas repetitivas.
---

# Auditoría de procesos

Objetivo: que salga con **un informe a su medida** y con la primera skill elegida, no con ideas genéricas.

## 1. Leer antes de preguntar
- `~/MI-SISTEMA-CLAUDE/perfil.md` (quién es, clientes, herramientas).
- Sus procesos en `~/MI-SISTEMA-CLAUDE/procesos/` o lo que pegue en el chat (fotos de una libreta también:
  transcribirlas). Si no hay nada, darle la plantilla de `references/escribir-un-proceso.md` (en esta skill).
- Hacer una lista numerada de los procesos que encontraste y mostrársela para confirmar que no falta ninguno.

## 2. Entrevista, proceso por proceso
- Usar `references/preguntas.md`. Solo las preguntas cuya respuesta **no** está escrita; con la herramienta de preguntas
  de Claude Code (AskUserQuestion): de a 3 o 4 por vez, cada una con 2 a 4 opciones armadas con lo que ya contó,
  y siempre puede escribir la suya. Las abiertas ("cuéntame los pasos") van en texto, de a una. Primero las de "lo mínimo", después las de "expandir".
- Al final de cada proceso, preguntar siempre una de "expandir el alcance" (lo que pasa antes y después del
  proceso suele ser lo más automatizable).
- Si la persona dice algo como regla o gusto, anotarlo en el perfil al momento.

## 3. Clasificar y puntuar cada proceso
Para cada uno, decidir el **tipo de ayuda** (ver `references/ideas-publicidad-video.md`):
- **A. Claude lo hace solo** (skill con script: renombrar, transcribir, convertir, armar carpetas).
- **B. Claude hace el primer borrador y la persona decide** (guiones, propuestas, copys, mails, informes).
- **C. Claude prepara y la persona ejecuta en su programa** (listas de cortes, prompts para IA de imagen,
  checklists de entrega).
- **D. Todavía no** (depende de un programa sin acceso, o es criterio puro que no conviene delegar). Decirlo
  claro y explicar por qué.

Puntaje (1 a 5 cada uno): **Frecuencia**, **Tiempo** que lleva, **Dolor** (cuánto le molesta), **Facilidad**
de automatizar. Prioridad = Frecuencia × Tiempo × Dolor × Facilidad. Mostrar la cuenta: que entienda por qué.

## 4. Escribir el informe
En `~/MI-SISTEMA-CLAUDE/auditoria/auditoria-<dd-mm-aaaa>.md`, con `references/plantilla-informe.md`.
Reglas:
- Hablarle a la persona por su nombre, con sus clientes y sus programas. Nada que sirva para cualquiera.
- Cada idea de skill con: nombre corto, qué pide la persona (la frase exacta que diría), qué hace Claude, qué
  necesita para empezar, cuánto tiempo ahorra por semana (estimado y explicado).
- **Quick win**: una que se pueda crear hoy mismo en menos de 30 minutos.
- Plan de 2 semanas: una skill por semana, en orden de prioridad.

## 5. Cerrar
- Resumen en el chat: los 3 primeros procesos con su puntaje y la quick win.
- Preguntar (🔔) si arrancamos ya la quick win con `crear-skill`.
- Sugerirle llevar un **diario de fricciones**: cada vez que repita algo o se frustre, una línea en
  `~/MI-SISTEMA-CLAUDE/procesos/fricciones.md`. En la próxima auditoría se lee primero.
