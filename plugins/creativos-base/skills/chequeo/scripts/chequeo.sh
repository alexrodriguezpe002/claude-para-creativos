#!/bin/bash
# chequeo.sh — revisa si esta computadora tiene todo lo que usa el kit. SOLO MIRA: no instala,
# no cambia ni borra nada. Mac y Linux (bash 3.2 o más nuevo). En Windows: chequeo.ps1.
#
# Cada línea es ✅ (está bien), ❌ (falta algo; el código entre corchetes dice qué arreglo
# corresponde en el SKILL.md) o ⚠️ (opcional o a revisar). Al final: el resumen y la lista de
# códigos.
#   bash chequeo.sh

HOME_DIR="${HOME:?}"
C="$HOME_DIR/.claude"
AQUI="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
PLUGIN_ROOT="$(cd "$AQUI/../../.." 2>/dev/null && pwd)"
OS="$(uname -s 2>/dev/null)"

OK=0; MAL=0; AVISO=0; CODIGOS=""
ok()    { OK=$((OK+1));     printf '✅ %s — %s\n' "$1" "$2"; }
mal()   { MAL=$((MAL+1));   CODIGOS="$CODIGOS $3"; printf '❌ %s — %s · arreglo: [%s]\n' "$1" "$2" "$3"; }
aviso() { AVISO=$((AVISO+1)); [ -n "$3" ] && CODIGOS="$CODIGOS $3"
          if [ -n "$3" ]; then printf '⚠️  %s — %s · [%s]\n' "$1" "$2" "$3"; else printf '⚠️  %s — %s\n' "$1" "$2"; fi; }
existe() { command -v "$1" >/dev/null 2>&1; }
# buscar FLAG cand1 cand2…: deja en ENCONTRADO el primer programa que de verdad arranca (FLAG = su
# opción de versión) y en ROTO el primero que existe pero no arranca (instalación rota).
buscar() {
  flag="$1"; shift; ENCONTRADO=""; ROTO=""
  for f in "$@"; do
    [ -n "$f" ] && [ -x "$f" ] || continue
    # en un subshell: si el programa aborta, el aviso del sistema ("Abort trap") no ensucia la lista
    if ( "$f" $flag; exit $? ) >/dev/null 2>&1; then ENCONTRADO="$f"; return 0; fi
    [ -z "$ROTO" ] && ROTO="$f"
  done
  return 1
}

# prefijo de los plugins del kit: el nombre de este plugin sin "-base" (creativos-base -> creativos-)
PREFIJO="creativos-"
if [ -f "$PLUGIN_ROOT/.claude-plugin/plugin.json" ]; then
  n=$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' "$PLUGIN_ROOT/.claude-plugin/plugin.json" | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
  case "$n" in *-base) PREFIJO="${n%base}" ;; esac
fi

DIAS="lun mar mié jue vie sáb dom"
dia=$(echo $DIAS | cut -d' ' -f"$(date +%u)")
echo "Chequeo del kit · $dia $(date '+%d-%m-%Y %H:%M')"
echo "(solo mira: no instala ni cambia nada)"
echo

# ------------------------------------------------------------------ 1. sistema
if [ "$OS" = "Darwin" ]; then
  ver=$(sw_vers -productVersion 2>/dev/null); arch=$(uname -m)
  [ "$arch" = "arm64" ] && chip="Apple Silicon" || chip="Intel"
  mayor=${ver%%.*}
  if [ "${mayor:-0}" -ge 12 ] 2>/dev/null; then ok "sistema" "macOS $ver · $chip ($arch)"
  else aviso "sistema" "macOS $ver es viejo: algunas herramientas piden macOS 12 o más nuevo" ""; fi
else
  ok "sistema" "$(uname -sr 2>/dev/null) · $(uname -m 2>/dev/null)"
fi

# ------------------------------------------------------------------ 2. git
if [ "$OS" = "Darwin" ]; then
  dev=$(/usr/bin/xcode-select -p 2>/dev/null)
  # /usr/bin/git sin las herramientas de Apple abre una ventana para instalarlas: solo se prueba si están
  clt=""; [ -n "$dev" ] && [ -x "$dev/usr/bin/git" ] && clt=/usr/bin/git
  if buscar --version /opt/homebrew/bin/git /usr/local/bin/git "$clt"; then
    ok "git" "$("$ENCONTRADO" --version 2>/dev/null | head -1)"
  elif [ -n "$ROTO" ]; then
    mal "git" "$ROTO está pero no arranca (instalación rota)" "git-mac"
  else
    mal "git" "no está (faltan las herramientas de línea de comandos de Apple; al instalarlas sale una ventana de Apple)" "git-mac"
  fi
else
  if buscar --version "$(command -v git 2>/dev/null)"; then ok "git" "$("$ENCONTRADO" --version 2>/dev/null | head -1)"
  else mal "git" "no está${ROTO:+ ($ROTO no arranca)}" "git-linux"; fi
fi

# ------------------------------------------------------------------ 3. gh (GitHub)
GH=""
buscar --version "$(command -v gh 2>/dev/null)" /usr/local/bin/gh /opt/homebrew/bin/gh && GH="$ENCONTRADO"
if [ -z "$GH" ]; then
  if [ -n "$ROTO" ]; then mal "gh (GitHub)" "$ROTO está pero no arranca (instalación rota)" "gh-instalar"
  else mal "gh (GitHub)" "no está (hace falta para proponer y revisar mejoras del kit)" "gh-instalar"; fi
else
  ok "gh (GitHub)" "$("$GH" --version 2>/dev/null | head -1)"
  estado=$("$GH" auth status 2>&1)
  if [ $? -eq 0 ]; then
    cuenta=$(printf '%s\n' "$estado" | grep -o 'account [A-Za-z0-9-]*' | head -1 | sed 's/account //')
    [ -z "$cuenta" ] && cuenta=$(printf '%s\n' "$estado" | grep -o 'as [A-Za-z0-9-]*' | head -1 | sed 's/as //')
    ok "GitHub: sesión" "conectado${cuenta:+ como $cuenta}"
  else
    mal "GitHub: sesión" "gh no tiene una cuenta conectada" "gh-login"
  fi
fi

# ------------------------------------------------------------------ 4. Python (hooks y scripts)
PY=""
if [ "$OS" = "Darwin" ]; then
  # los mismos lugares, en el mismo orden, que usan los hooks del kit (hooks/lanzar.sh)
  enpath=$(command -v python3 2>/dev/null); [ "$enpath" = "/usr/bin/python3" ] && enpath=""
  cltpy=""; [ -n "$dev" ] && [ -x "$dev/usr/bin/python3" ] && cltpy="$dev/usr/bin/python3"
  buscar --version /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/Current/bin/python3 "$enpath" "$cltpy" && PY="$ENCONTRADO"
else
  buscar --version "$(command -v python3 2>/dev/null)" "$(command -v python 2>/dev/null)" && PY="$ENCONTRADO"
fi
if [ -z "$PY" ] && [ -n "$ROTO" ]; then
  mal "Python" "$ROTO está pero no arranca (instalación rota)" "python-instalar"
elif [ -n "$PY" ]; then
  v=$("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)
  case "$v" in
    3.[0-6].*|2.*) mal "Python" "$v es muy viejo (hace falta 3.7 o más nuevo)" "python-instalar" ;;
    *) ok "Python" "$v ($PY)" ;;
  esac
else
  mal "Python" "no está (sin Python no funcionan el registro de proyectos ni varios scripts)" "python-instalar"
fi

# ------------------------------------------------------------------ 5. plugins del kit
INST="$C/plugins/installed_plugins.json"
instalados=""
if [ -f "$INST" ]; then
  instalados=$(grep -o "\"$PREFIJO[A-Za-z0-9_-]*@[A-Za-z0-9._-]*\"" "$INST" | tr -d '"' | sort -u | tr '\n' ' ')
fi
sincronizados=""
if [ -d "$C/plugins/synced" ]; then
  for f in "$C"/plugins/synced/*/*/.claude-plugin/plugin.json "$C"/plugins/synced/*/*/*/.claude-plugin/plugin.json; do
    [ -f "$f" ] || continue
    n=$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' "$f" | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
    case "$n" in "$PREFIJO"*) sincronizados="$sincronizados $n" ;; esac
  done
fi
todos="$instalados$sincronizados"
# Los apagados en settings.json ("enabledPlugins": {"creativos-video@creativos": false}) no cuentan.
apagados=""
[ -f "$C/settings.json" ] && apagados=$(grep -o "\"$PREFIJO[A-Za-z0-9_-]*@[A-Za-z0-9._-]*\"[[:space:]]*:[[:space:]]*false" "$C/settings.json" | sed 's/^"\([^"@]*\)@.*/\1/' | tr '\n' ' ' | sed 's/ *$//')
tiene() { case " $apagados " in *" $1 "*) return 1 ;; esac
          case " $todos " in *" $1@"*|*" $1 "*) return 0 ;; esac; return 1; }
if tiene "${PREFIJO}base"; then
  ok "plugins del kit" "$(echo $instalados | sed 's/@[^ ]*//g')${sincronizados:+ · desde la app:$sincronizados}${apagados:+ · apagados: $apagados}"
else
  mal "plugins del kit" "no está instalado ${PREFIJO}base" "plugins-instalar"
fi
# Qué grupos usa la persona: lo que eligió en plugins-elegir, guardado en ~/MI-SISTEMA-CLAUDE/grupos.txt. Sobrevive a
# reinstalar el kit (quitar la tienda borra lo prendido y apagado: repaso del vie 20-11-2026) y no vuelve a avisar a
# quien usa los 3 grupos. Cada plugin de más suma skills a cada sesión.
GRUPOS_TXT="$HOME_DIR/MI-SISTEMA-CLAUDE/grupos.txt"
if tiene "${PREFIJO}base"; then
  if [ -f "$GRUPOS_TXT" ]; then
    elegidos=$(tr -s ' \t\r\n,' '\n' < "$GRUPOS_TXT" | grep -E '^(video|animacion|oficina)$' | sort -u | tr '\n' ' ' | sed 's/ *$//')
    faltan=""; sobran=""
    for g in video animacion oficina; do
      case " $elegidos " in
        *" $g "*) tiene "${PREFIJO}$g" || faltan="$faltan $g" ;;
        *) if tiene "${PREFIJO}$g"; then sobran="$sobran $g"; fi ;;
      esac
    done
    if [ -n "$faltan" ]; then
      aviso "grupos elegidos" "elegiste${faltan} pero no está instalado o está apagado" "plugins-elegir"
    elif [ -n "$sobran" ]; then
      aviso "plugins de más" "está prendido${sobran} y no lo elegiste: suma skills a cada sesión" "plugins-elegir"
    else
      ok "grupos elegidos" "${elegidos:-solo el base}"
    fi
  else
    aviso "grupos" "falta elegir qué haces (video, animación, procesos) para dejar solo esos plugins" "plugins-elegir"
  fi
fi
VIDEO=0
if tiene "${PREFIJO}video" || tiene "${PREFIJO}animacion"; then VIDEO=1; fi

# instalación vieja (v1): skills del kit sueltas en ~/.claude/skills o hooks en settings.json
LISTA="$AQUI/../references/skills-v1.txt"
viejas=0
if [ -f "$LISTA" ]; then
  while read -r s _; do
    case "$s" in ''|'#'*) continue ;; esac
    [ -d "$C/skills/$s" ] && viejas=$((viejas+1))
  done < "$LISTA"
fi
hooksv1=0
[ -f "$C/settings.json" ] && grep -q 'skills/mdfilesummary/scripts/md_files.py' "$C/settings.json" && hooksv1=1
if [ $viejas -gt 0 ] || [ $hooksv1 -eq 1 ]; then
  aviso "instalación vieja (v1)" "$viejas skills del kit en ~/.claude/skills$([ $hooksv1 -eq 1 ] && echo ' y sus hooks en settings.json')" "v1-migrar"
fi

# ------------------------------------------------------------------ 6. ffmpeg y node (video/animación)
if [ $VIDEO -eq 1 ]; then
  # se prueba primero el que encuentran las sesiones (el del PATH): si ese está roto, falla aunque haya otro
  enpath=$(command -v ffmpeg 2>/dev/null)
  if [ -n "$enpath" ]; then buscar -version "$enpath"; else buscar -version /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg "$HOME_DIR/.local/bin/ffmpeg"; fi
  if [ -n "$ENCONTRADO" ]; then ok "ffmpeg" "$("$ENCONTRADO" -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
  elif [ -n "$ROTO" ]; then mal "ffmpeg" "$ROTO está pero no arranca (instalación rota)" "ffmpeg-instalar"
  else mal "ffmpeg" "no está (lo usan las skills de video y de animación)" "ffmpeg-instalar"; fi
  enpath=$(command -v node 2>/dev/null)
  if [ -n "$enpath" ]; then buscar --version "$enpath"; else buscar --version /usr/local/bin/node /opt/homebrew/bin/node; fi
  NODE="$ENCONTRADO"
  npx="$(dirname "${NODE:-/x}")/npx"; [ -x "$npx" ] || npx=$(command -v npx 2>/dev/null)
  if [ -n "$NODE" ] && [ -n "$npx" ] && PATH="$(dirname "$NODE"):$PATH" "$npx" --version >/dev/null 2>&1; then
    ok "node y npx" "node $("$NODE" --version 2>/dev/null) ($NODE)"
  elif [ -n "$ROTO" ]; then
    mal "node y npx" "$ROTO está pero no arranca (instalación rota)" "node-instalar"
  elif [ -n "$NODE" ]; then
    mal "node y npx" "hay node ($NODE) pero npx no anda" "node-instalar"
  else
    mal "node y npx" "no está (lo usa HyperFrames y los controles de calidad)" "node-instalar"
  fi
fi

# ------------------------------------------------------------------ 7. memoria única
SET="$C/settings.json"
mem=""
[ -f "$SET" ] && mem=$(grep -o '"autoMemoryDirectory"[[:space:]]*:[[:space:]]*"[^"]*"' "$SET" | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
if [ -n "$mem" ]; then
  ok "memoria" "una sola, en $mem"
else
  esc=$(printf '%s' "$HOME_DIR" | sed 's/[^A-Za-z0-9]/-/g')
  if [ -f "$C/projects/$esc/memory/MEMORY.md" ]; then
    mal "memoria" "cada carpeta tiene su memoria (sugerida: la que ya existe, $C/projects/$esc/memory)" "memoria-unica"
  else
    mal "memoria" "cada carpeta tiene su memoria (sugerida: $HOME_DIR/MI-SISTEMA-CLAUDE/memoria)" "memoria-unica"
  fi
fi

# ------------------------------------------------------------------ 7b. carpeta de proyectos
CJ="$C/registro-proyectos/carpetas.json"
if [ -f "$CJ" ] && grep -q '"raices"' "$CJ"; then
  ok "carpeta de proyectos" "la que dice ~/.claude/registro-proyectos/carpetas.json"
elif [ -d "$HOME_DIR/PROYECTOS" ]; then
  ok "carpeta de proyectos" "$HOME_DIR/PROYECTOS"
else
  mal "carpeta de proyectos" "no hay ~/PROYECTOS ni otra declarada (sin ella, Claude inventa dónde guardar cada trabajo)" "proyectos-carpeta"
fi

# ------------------------------------------------------------------ 8. perfil
if [ -f "$C/CLAUDE.md" ] && grep -q 'MI-SISTEMA-CLAUDE/perfil.md' "$C/CLAUDE.md"; then
  if [ -f "$HOME_DIR/MI-SISTEMA-CLAUDE/perfil.md" ] && [ "$(grep -c '[^[:space:]]' "$HOME_DIR/MI-SISTEMA-CLAUDE/perfil.md")" -gt 5 ]; then
    ok "perfil" "~/.claude/CLAUDE.md lee ~/MI-SISTEMA-CLAUDE/perfil.md"
  else
    mal "perfil" "el CLAUDE.md lo busca, pero el perfil está vacío o no existe" "perfil-conoceme"
  fi
elif [ -f "$C/CLAUDE.md" ]; then
  mal "perfil" "~/.claude/CLAUDE.md existe pero no lee el perfil" "perfil-conoceme"
elif [ -f "$HOME_DIR/CLAUDE.md" ]; then
  mal "perfil" "no hay ~/.claude/CLAUDE.md (hay uno en ~/CLAUDE.md: solo lo leen las sesiones abiertas dentro de tu carpeta de usuario)" "perfil-conoceme"
else
  mal "perfil" "no hay ~/.claude/CLAUDE.md ni perfil" "perfil-conoceme"
fi

# ------------------------------------------------------------------ 9. avisos al celular (opcional)
if [ -f "$SET" ] && grep -q '"inputNeededNotifEnabled"[[:space:]]*:[[:space:]]*true' "$SET" \
   && grep -q '"agentPushNotifEnabled"[[:space:]]*:[[:space:]]*true' "$SET"; then
  ok "avisos al celular" "activados"
else
  aviso "avisos al celular" "apagados (opcional: avisan cuando Claude necesita algo o termina)" "avisos-celular"
fi

echo
echo "Resumen: $OK ✅ · $MAL ❌ · $AVISO ⚠️"
echo "CODIGOS:${CODIGOS:- ninguno}"
exit 0
