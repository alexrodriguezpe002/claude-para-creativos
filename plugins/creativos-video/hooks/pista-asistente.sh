#!/bin/sh
# Pista para «¿ya está el timeline?» (plugin creativos-video). Si el asistente de edición está instalado en esta
# computadora y la persona pregunta por el timeline o la sincronización, le dice a Claude dónde mirar antes de
# buscar en otro lado. Sin asistente instalado no dice nada. Nunca frena a Claude: siempre sale con 0.
# Por qué: en el usuario de prueba (jue 19-11-2026) una sesión nueva contestó «no encontré ningún timeline» cuando
# el asistente ya lo había armado.
conf="$HOME/MI-SISTEMA-CLAUDE/asistente-edicion/config.json"
[ -f "$conf" ] || exit 0
pedido=$(sed -E -n 's/.*"prompt"[[:space:]]*:[[:space:]]*"(([^"\\]|\\.)*)".*/\1/p' | head -c 4000)
printf '%s' "$pedido" | grep -i -q -E 'timeline|l(í|i|\\u00ed)nea de tiempo|sincroni|shotput|el asistente' || exit 0
dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd) || exit 0
motor="$dir/../skills/asistente-de-edicion/scripts/asistente.py"
echo "🎬 El asistente de edición está instalado en esta computadora (skill asistente-de-edicion). Si preguntan si ya está el timeline, cuál fue el último o qué clips quedaron para revisar, primero su estado: \"$HOME/.claude/venv-video/bin/python\" \"$motor\" --estado (en Windows, el python de %USERPROFILE%\\.claude\\venv-video\\Scripts). Contestar con eso, en dos líneas; no buscar en otro lado ni ofrecer armarlo de nuevo."
exit 0
