#!/bin/zsh
# Arranque del modo «siempre conectado» en Mac. Lo lanza launchd al iniciar sesión y cada vez
# que el servidor se cae (KeepAlive). Vive copiado en ~/MI-SISTEMA-CLAUDE/celular/ porque la
# carpeta del plugin cambia con cada actualización del kit y launchd necesita una ruta fija.
# Todo lo que pasa queda en ~/MI-SISTEMA-CLAUDE/celular/celular.log.

source "${0:A:h}/comun.sh" || exit 0
LOG=$CELULAR_DIR/celular.log
mkdir -p "$CELULAR_DIR"
anotar() { print -r -- "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

# que el registro no crezca sin fin (queda el anterior como .1)
if [[ -f $LOG ]] && (( $(stat -f%z "$LOG" 2>/dev/null || print 0) > 1048576 )); then
  mv -f "$LOG" "$LOG.1"
fi

CARPETA=""
[[ -f $CELULAR_DIR/carpeta.txt ]] && CARPETA=$(<"$CELULAR_DIR/carpeta.txt")
CARPETA=${CARPETA:-$CARPETA_POR_DEFECTO}

# Cada problema conocido espera antes de salir, así launchd no lo relanza cada 30 segundos.
if ! bin=$(buscar_claude); then
  anotar "SIN CLAUDE: no encuentro Claude Code con Remote Control"; sleep 300; exit 0
fi
if ! cuenta "$bin" >/dev/null; then
  anotar "SIN SESION: falta iniciar sesión (conectar una vez a mano)"; sleep 300; exit 0
fi
pv=$(primera_vez "$CARPETA")
if [[ $pv != "dialogo=true confianza=true" ]]; then
  # sin terminal no se pueden responder «Enable Remote Control?» ni «Trust …?»
  anotar "FALTA primera vez en $CARPETA ($pv)"; sleep 600; exit 0
fi
if ya=$(servidores | head -1) && [[ -n $ya ]]; then
  anotar "ESPERA ya hay otra conexión abierta (pid ppid segundos carpeta: $ya)"; sleep 60; exit 0
fi
if ! cd "$CARPETA" 2>/dev/null; then
  anotar "SIN CARPETA: no existe $CARPETA"; sleep 300; exit 0
fi

spawn=()
"$bin" remote-control --help 2>/dev/null | grep -q -- '--spawn' && spawn=(--spawn=same-dir)
anotar "ARRANCA Claude Code $(version_de "$bin") en $CARPETA"

# Enchufada, que no se duerma mientras corre. -w $$: hasta que termine ESTE proceso, que con el
# exec de abajo pasa a ser claude (mismo número de proceso).
/usr/bin/caffeinate -s -w $$ &!

# exec: el proceso que lanzó launchd pasa a ser claude, así los avisos de permisos de macOS
# nombran a «claude» y no a «zsh». Sin las variables que le roban la conexión (ver comun.sh).
preparar_env_limpio
exec env "${ENV_U[@]}" "$bin" remote-control "${spawn[@]}" --verbose
