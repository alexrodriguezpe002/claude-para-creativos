#!/bin/sh
# Pone la lista del equipo «en la mesa» al empezar cada conversación (hook SessionStart del plugin base
# del equipo): lo que imprime este script lo lee Claude como contexto. Nunca frena a Claude: si falta la
# lista o todavía no tiene personas, no dice nada. Tope: 80 líneas y unos 8000 caracteres; lo que pase de
# eso queda para la skill equipo. Funciona con el sh de Mac y Linux y con el de Git Bash en Windows.
# Lo instala `ficha.py plantilla` (skill ficha-de-equipo).

dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd) || exit 0
lista="$dir/../equipo/EQUIPO.md"
[ -f "$lista" ] || exit 0
grep -q '^- \*\*' "$lista" 2>/dev/null || exit 0

salida=$(awk -v max=80 -v tope=8000 'NR > max { exit } { n += length($0) + 1; if (n > tope) exit; print }' "$lista" 2>/dev/null) || exit 0
[ -n "$salida" ] || exit 0
printf '%s\n' "$salida"

total=$(grep -c '^- \*\*' "$lista" 2>/dev/null)
filas=$(printf '%s\n' "$salida" | grep -c '^- \*\*')
if [ "${total:-0}" -gt "${filas:-0}" ] 2>/dev/null; then
  printf '\n(La lista sigue: son %s personas y aquí van %s. El resto, con la skill equipo.)\n' "$total" "$filas"
fi
exit 0
