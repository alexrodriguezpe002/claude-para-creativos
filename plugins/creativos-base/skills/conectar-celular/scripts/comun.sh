# comun.sh — lo que comparten los scripts de conectar-celular en Mac.
# Se carga con:  source "${0:A:h}/comun.sh"
# Sin Python a propósito: en una Mac nueva, python3 abre la ventana de Apple para instalar herramientas.

CELULAR_DIR=${CELULAR_DIR:-$HOME/MI-SISTEMA-CLAUDE/celular}   # modo automático: copia del arranque y registro
ETIQUETA=com.creativos.conectar-celular                       # nombre del agente de launchd
VERSION_MINIMA=2.1.139                                        # la primera versión con Remote Control
CARPETA_POR_DEFECTO=$HOME/PROYECTOS                           # nunca la carpeta de inicio (ver abajo)
CLAUDE_JSON=${CLAUDE_JSON:-$HOME/.claude.json}

# Por qué no la carpeta de inicio: en ~ Claude Code nunca guarda la confianza, así que
# `claude remote-control` pregunta «Trust …? [y/N]» CADA vez que arranca, y sin terminal
# (modo automático) ni siquiera arranca («Workspace not trusted»). En ~/PROYECTOS se
# responde una sola vez.

# Patrón del servidor: «…/claude remote-control …» o «claude rc …» (no «claude --remote-control»,
# que es una sesión común conectada).
PATRON_SERVIDOR='(^|/)claude(\.exe)? (remote-control|rc)( |$)'

# «2.1.326» de un binario, o nada
version_de() {
  "$1" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

# ¿$1 >= $2? (por partes: 2.1.40 < 2.1.139)
version_ge() {
  local -a a b
  local i
  a=(${(s:.:)1}); b=(${(s:.:)2})
  for i in 1 2 3; do
    (( ${a[i]:-0} > ${b[i]:-0} )) && return 0
    (( ${a[i]:-0} < ${b[i]:-0} )) && return 1
  done
  return 0
}

# Todos los Claude Code de esta Mac, del más nuevo al más viejo: primero los que trae la app de
# escritorio (claude-code/<versión>/claude.app o claude-code/<versión>/<código>/claude.app; la
# forma cambió en 2026-11), después el instalador oficial, Homebrew y el del PATH.
candidatos_claude() {
  local base="$HOME/Library/Application Support/Claude/claude-code" c i
  local -a versiones
  versiones=("$base"/*(Nn/))
  for (( i=${#versiones}; i>0; i-- )); do
    for c in "${versiones[i]}/claude.app/Contents/MacOS/claude" \
             "${versiones[i]}"/*/claude.app/Contents/MacOS/claude(N); do
      [[ -x $c ]] && print -r -- "$c"
    done
  done
  for c in "$HOME/.local/bin/claude" /opt/homebrew/bin/claude /usr/local/bin/claude \
           "$(whence -p claude 2>/dev/null)"; do
    [[ -n $c && -x $c ]] && print -r -- "$c"
  done
}

# El primero que tiene Remote Control. CLAUDE_BIN lo fija (pruebas).
buscar_claude() {
  if [[ -n $CLAUDE_BIN ]]; then print -r -- "$CLAUDE_BIN"; return 0; fi
  local c ver
  for c in "${(@f)$(candidatos_claude)}"; do
    [[ -n $c ]] || continue
    ver=$(version_de "$c")
    [[ -n $ver ]] && version_ge "$ver" "$VERSION_MINIMA" && { print -r -- "$c"; return 0 }
  done
  return 1
}

# Cuenta con la que está iniciada la sesión del CLI ($1 = binario). Sale con 1 si no hay sesión.
cuenta() {
  local out k
  local -a vals
  out=$("$1" auth status 2>/dev/null) || return 1
  [[ $out =~ '"loggedIn"[[:space:]]*:[[:space:]]*true' ]] || return 1
  for k in email emailAddress orgName organizationName; do
    if [[ $out =~ "\"$k\"[[:space:]]*:[[:space:]]*\"([^\"]+)\"" ]]; then
      vals+=("$match[1]")
    fi
  done
  print -r -- "${(j: · :)vals:-tu cuenta}"
}

# Corre un comando sin las variables que le roban la conexión a Remote Control: si este script
# lo lanza otra sesión de Claude (y no la persona), hereda ANTHROPIC_BASE_URL y otras de la app,
# y el servidor falla con «only available when using Claude via api.anthropic.com» o similar.
preparar_env_limpio() {   # deja en ENV_U los «-u VARIABLE» para `env`
  local linea nombre
  ENV_U=()
  for linea in "${(@f)$(env)}"; do
    nombre=${linea%%=*}
    [[ $nombre == (ANTHROPIC_*|CLAUDECODE|CLAUDE_CODE_*|CLAUDE_AGENT_SDK_*|DISABLE_GROWTHBOOK) ]] && ENV_U+=(-u "$nombre")
  done
}
env_limpio() {
  preparar_env_limpio
  env "${ENV_U[@]}" "$@"
}

# «[[dd-]hh:]mm:ss» (etime de ps) → segundos
segundos() {
  local t=$1 d=0 h=0 m=0 s=0
  local -a p
  if [[ $t == *-* ]]; then d=${t%%-*}; t=${t#*-}; fi
  p=(${(s.:.)t})
  case ${#p} in
    3) h=${p[1]}; m=${p[2]}; s=${p[3]} ;;
    2) m=${p[1]}; s=${p[2]} ;;
    1) s=${p[1]} ;;
  esac
  print $(( d*86400 + h*3600 + m*60 + s ))
}

# 125 → «2 min», 7300 → «2 h 1 min»
duracion() {
  local s=$1
  if (( s < 60 )); then print "$s s"
  elif (( s < 3600 )); then print "$(( s/60 )) min"
  elif (( s < 86400 )); then print "$(( s/3600 )) h $(( s%3600/60 )) min"
  else print "$(( s/86400 )) días"; fi
}

# Servidores de Remote Control de ESTE usuario (otro usuario de la Mac no cuenta), uno por línea:
#   «pid ppid segundos carpeta»
# $1 (opcional) = solo los que trabajan en esa carpeta. Si se pasa CELULAR_PATRON, se usa ese patrón (pruebas).
servidores() {
  local filtro=$1 pid ppid etime cmd dir
  ps -x -U "$UID" -o pid=,ppid=,etime=,command= 2>/dev/null | while read -r pid ppid etime cmd; do
    # el envoltorio (caffeinate o env) no es otro servidor: es el mismo
    [[ $cmd == caffeinate* || $cmd == /usr/bin/caffeinate* || $cmd == env\ * || $cmd == /usr/bin/env\ * ]] && continue
    [[ $cmd =~ ${CELULAR_PATRON:-$PATRON_SERVIDOR} ]] || continue
    dir=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)
    [[ -n $filtro && $dir != $filtro ]] && continue
    print -r -- "$pid $ppid $(segundos "$etime") $dir"
  done
}

# Conexiones abiertas con internet de un proceso (si habla con Claude, hay al menos una)
conexiones() {
  local n
  n=$(lsof -a -p "$1" -i TCP -s TCP:ESTABLISHED -n -P 2>/dev/null | grep -c ESTABLISHED)
  print ${n:-0}
}

# ¿Ya se respondieron las dos preguntas de la primera vez? ($1 = carpeta)
#   «Enable Remote Control? (y/n)» → remoteDialogSeen en ~/.claude.json
#   «Trust <carpeta>? [y/N]»       → projects[<carpeta>].hasTrustDialogAccepted, o el de una carpeta madre:
#                                     la confianza se hereda (si la carpeta de usuario ya es de confianza, no
#                                     pregunta en ~/PROYECTOS; visto en el usuario de prueba, jue 19-11-2026)
# Imprime «dialogo=true|false confianza=true|false». Lee el JSON con JavaScript de macOS (sin Python).
primera_vez() {
  /usr/bin/osascript -l JavaScript - "$1" "$CLAUDE_JSON" 2>/dev/null <<'JXA'
function run(argv) {
  ObjC.import('Foundation');
  const s = $.NSString.stringWithContentsOfFileEncodingError(argv[1], $.NSUTF8StringEncoding, null);
  if (!s || !s.js) return 'dialogo=false confianza=false';
  let d;
  try { d = JSON.parse(s.js); } catch (e) { return 'dialogo=false confianza=false'; }
  const pr = d.projects || {};
  let dir = argv[0].replace(/\/+$/, '') || '/';
  let conf = false;
  for (;;) {
    const p = pr[dir];
    if (p && p.hasTrustDialogAccepted === true) { conf = true; break; }
    if (dir === '/') break;
    const i = dir.lastIndexOf('/');
    dir = i <= 0 ? '/' : dir.slice(0, i);
  }
  return 'dialogo=' + (d.remoteDialogSeen === true) + ' confianza=' + conf;
}
JXA
}

# ¿Está instalado el modo automático (agente de launchd cargado)?
agente_cargado() {
  launchctl print "gui/$UID/$ETIQUETA" >/dev/null 2>&1
}

# Traduce el final del registro del modo automático a una frase (o nada si no reconoce nada).
diagnostico_registro() {
  local log=$CELULAR_DIR/celular.log t
  [[ -f $log ]] || return 0
  t=$(tail -n 60 "$log" 2>/dev/null | sed $'s/\x1b\\[[0-9;?]*[A-Za-z]//g')
  case $t in
    *"ESPERA ya hay otra conexión"*)        print "Espera: ya hay otra conexión abierta (por ejemplo en una pestaña de la terminal). Cuando se cierre, el modo automático la reemplaza solo." ;;
    *"Workspace not trusted"*|*"FALTA primera vez"*)
                                            print "Falta responder una vez a mano las preguntas de la primera vez en esa carpeta: conectar con la pestaña de la terminal (conectar-celular.command), responder y, y volver a instalar." ;;
    *"got no answer"*)                      print "Falta responder «Enable Remote Control? (y/n)» una vez a mano: conectar con la pestaña de la terminal y escribir y." ;;
    *"must be logged in"*|*"requires a claude.ai subscription"*|*"SIN SESION"*)
                                            print "Se cerró la sesión de Claude en la computadora: conectar una vez con la pestaña de la terminal (abre el navegador para entrar)." ;;
    *"isn't enabled for this account"*)     print "La cuenta no tiene Remote Control habilitado (plan Pro o superior). Cerrar y abrir sesión lo refresca." ;;
    *"Couldn't verify Remote Control eligibility"*|*"ENOTFOUND"*|*"ECONNREFUSED"*)
                                            print "Sin internet o algo bloquea la conexión. Vuelve a intentar solo cada 30 segundos." ;;
    *"SIN CLAUDE"*)                         print "No encuentra Claude Code: abrir la app de Claude y entrar una vez a la pestaña Code." ;;
    *"Connected"*)                          print "El registro dice Connected." ;;
  esac
}
