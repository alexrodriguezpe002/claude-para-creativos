#!/bin/sh
# Lanza los hooks del kit (plugin creativos-base). Nunca frena a Claude: si falta Python, el
# sonido o el script, sale con 0 sin decir nada. Funciona con el sh de Mac y Linux y con el de
# Git Bash en Windows.
#
#   lanzar.sh sonido     sonido al terminar cada respuesta (solo Mac; se apaga creando ~/.claude/sin-sonido)
#   lanzar.sh post-tool  registro MD FILES después de cada herramienta
#   lanzar.sh prompt     registro MD FILES cuando la persona nombra un proyecto, y el respaldo diario a su
#                        GitHub privado (skill respaldar: una vez por día, en segundo plano, sin demorar nada)
#   lanzar.sh stop       registro MD FILES al terminar la respuesta (recordatorio + índice)

evento="${1:-}"
dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd) || exit 0

if [ "$evento" = "sonido" ]; then
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] || exit 0
  [ -f "$HOME/.claude/sin-sonido" ] && exit 0
  sonido=/System/Library/Sounds/Glass.aiff
  if [ -x /usr/bin/afplay ] && [ -f "$sonido" ]; then
    ( /usr/bin/afplay "$sonido" >/dev/null 2>&1 & )
  fi
  exit 0
fi

anda() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' >/dev/null 2>&1; }

# Cada candidato se prueba de verdad: un Python instalado puede estar roto (le falta una librería)
# y el "python3" de la Tienda de Windows es un atajo que no anda.
buscar_python() {
  if [ "$(uname -s 2>/dev/null)" = "Darwin" ]; then
    # En Mac, /usr/bin/python3 sin las herramientas de Apple abre una ventana para instalarlas:
    # nunca se usa ese; sí el de las herramientas, si están instaladas.
    enpath=$(command -v python3 2>/dev/null); [ "$enpath" = "/usr/bin/python3" ] && enpath=""
    dev=$(/usr/bin/xcode-select -p 2>/dev/null) || dev=""
    for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
             /Library/Frameworks/Python.framework/Versions/Current/bin/python3 "$enpath" \
             "${dev:+$dev/usr/bin/python3}"; do
      if [ -n "$p" ] && [ -x "$p" ] && anda "$p"; then echo "$p"; return 0; fi
    done
    return 1
  fi
  # Windows (Git Bash) y Linux
  for p in python3 python py; do
    if command -v "$p" >/dev/null 2>&1 && anda "$p"; then echo "$p"; return 0; fi
  done
  return 1
}

case "$evento" in
  post-tool|prompt|stop) ;;
  *) exit 0 ;;
esac
script="$dir/../skills/mdfilesummary/scripts/md_files.py"
[ -f "$script" ] || script=""
respaldo="$dir/../skills/respaldar/scripts/respaldar.py"
[ "$evento" = "prompt" ] && [ -f "$respaldo" ] || respaldo=""
[ -n "$script$respaldo" ] || exit 0

# El Python que anduvo queda anotado (una búsqueda por sesión de la computadora, no por evento). Si
# deja de arrancar (código 126 o más: no está, roto o abortó al cargar), se busca otro una vez.
memo="${TMPDIR:-/tmp}/claude-kit-python-$(id -u 2>/dev/null || echo 0)"
entrada=$(cat)
py=$(cat "$memo" 2>/dev/null)
if [ -z "$py" ] || ! command -v "$py" >/dev/null 2>&1; then
  py=$(buscar_python) || exit 0
  printf '%s' "$py" > "$memo" 2>/dev/null
fi
tarea() {
  if [ "$1" = registro ]; then
    printf '%s' "$entrada" | "$py" "$script" "$evento"
  else
    "$py" "$respaldo" --si-toca </dev/null
  fi
}
for t in registro respaldo; do
  [ "$t" = registro ] && [ -z "$script" ] && continue
  [ "$t" = respaldo ] && [ -z "$respaldo" ] && continue
  tarea "$t"
  if [ $? -ge 126 ]; then
    rm -f "$memo" 2>/dev/null
    py=$(buscar_python) || exit 0
    printf '%s' "$py" > "$memo" 2>/dev/null
    tarea "$t"
  fi
done
exit 0
