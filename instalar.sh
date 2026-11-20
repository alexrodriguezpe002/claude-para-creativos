#!/bin/zsh
# Instala o actualiza el kit desde la terminal de la Mac. Es el RESPALDO: lo normal es instalarlo desde la
# app (INSTALAR.md). Usa el comando `claude` (el de la terminal o el que trae la app de escritorio).
#
#   zsh instalar.sh                              plugin base + pregunta qué grupos (video, animacion, oficina)
#   zsh instalar.sh --grupos "video animacion"   plugin base + esos grupos, sin preguntar
#   zsh instalar.sh --actualizar                 pone al día los plugins; si quedó la versión 1 del kit, la
#                                                pasa a la 2 (mueve las skills viejas, no las borra)
#   … --carpeta                                  usar esta carpeta como fuente, sin ir a GitHub
#
# No escribe tu CLAUDE.md, tu perfil ni tu memoria (eso lo hacen las skills chequeo y conoceme, con permiso).
set -u
KIT="${0:A:h}"
C="$HOME/.claude"
ACTUALIZAR=0; GRUPOS=""; SOLO_CARPETA=0
while (( $# )); do
  case "$1" in
    --actualizar) ACTUALIZAR=1 ;;
    --grupos) shift; GRUPOS="${1:-}" ;;
    --carpeta) SOLO_CARPETA=1 ;;
    *) print -u2 "Opción desconocida: $1"; exit 2 ;;
  esac
  shift
done
say() { print -P "%B$1%b"; }

MKT=$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' "$KIT/.claude-plugin/marketplace.json" 2>/dev/null | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
BASE_DIR="$KIT/plugins/creativos-base"
if [[ -z "$MKT" || ! -d "$BASE_DIR" ]]; then
  print "Esta carpeta no tiene el kit versión 2 ($KIT). Baja lo último con: git -C \"$KIT\" pull"; exit 1
fi
LISTA="$BASE_DIR/skills/chequeo/references/skills-v1.txt"

# 1. El comando claude: el de la terminal o el que trae la app (la versión más nueva)
CLI=$(command -v claude 2>/dev/null)
if [[ -z "$CLI" ]]; then
  for f in "$HOME/Library/Application Support/Claude/claude-code/"*/{*/,}claude.app/Contents/MacOS/claude(NnOn); do
    [[ -x "$f" ]] && CLI="$f" && break
  done
fi
if [[ -z "$CLI" ]]; then
  print "No encontré el comando claude. Instala el kit desde la app de Claude (INSTALAR.md, paso 2) y después"
  print "dile a Claude: \"haz el chequeo\". No se cambió nada."
  exit 0
fi
cl() { "$CLI" "$@"; }

# 2. El marketplace: desde GitHub si esta carpeta viene de ahí; si no se puede, desde esta carpeta
say "1/4 · Marketplace \"$MKT\""
if grep -q "\"$MKT\"[[:space:]]*:" "$C/plugins/known_marketplaces.json" 2>/dev/null; then
  cl plugin marketplace update "$MKT" >/dev/null 2>&1 && print "   al día" || print "   ⚠️  no pude actualizarlo (sigo con lo que hay)"
else
  REPO=""
  if (( ! SOLO_CARPETA )); then
    url=$(git -C "$KIT" remote get-url origin 2>/dev/null)
    [[ "$url" =~ 'github\.com[:/]+([^/]+)/([^/]+)$' ]] && REPO="${match[1]}/${match[2]%.git}"
  fi
  # GIT_TERMINAL_PROMPT=0: si GitHub pide usuario y contraseña, falla enseguida en vez de quedarse esperando
  if [[ -n "$REPO" ]] && GIT_TERMINAL_PROMPT=0 "$CLI" plugin marketplace add "$REPO" >/dev/null 2>&1; then
    print "   agregado desde GitHub: $REPO"
  elif cl plugin marketplace add "$KIT" >/dev/null 2>&1; then
    print "   agregado desde esta carpeta: $KIT"
    [[ -n "$REPO" ]] && print "   (no se pudo usar GitHub: para actualizar, primero git -C \"$KIT\" pull)"
  else
    print "   ❌ No pude agregar el marketplace. Instala el kit desde la app (INSTALAR.md). No se cambió nada."
    exit 1
  fi
fi

# 3. Qué plugins: el base siempre; los grupos, según lo pedido o (al actualizar) según lo que ya usaba
say "2/4 · Plugins"
typeset -U quiero
quiero=(creativos-base)
if [[ -n "$GRUPOS" ]]; then
  GRUPOS=${GRUPOS//,/ }
  for g in ${=GRUPOS}; do quiero+=("creativos-${g#creativos-}"); done
elif (( ACTUALIZAR )); then
  # los grupos que ya tiene instalados y los de las skills de la versión 1 que tenga sueltas
  for k in $(grep -o '"creativos-[a-z]*@'"$MKT"'"' "$C/plugins/installed_plugins.json" 2>/dev/null | tr -d '"'); do
    quiero+=("${k%@*}")
  done
  while read -r s p; do
    [[ -z "$s" || "$s" == \#* ]] && continue
    [[ -d "$C/skills/$s" ]] && quiero+=("$p")
  done < "$LISTA"
elif [[ -t 0 ]]; then
  print "   ¿Qué grupos instalo además del base? Escribe los que quieras, separados por espacio:"
  print "   video (editar, subtítulos, música) · animacion (HyperFrames) · oficina (procesos). Enter = ninguno."
  read "resp?   > "
  for g in ${=resp}; do quiero+=("creativos-${g#creativos-}"); done
fi
for p in $quiero; do
  if [[ ! -d "$KIT/plugins/$p" ]]; then print "   ⚠️  no existe el grupo ${p#creativos-} (hay: video, animacion, oficina)"; continue; fi
  if grep -q "\"$p@$MKT\"" "$C/plugins/installed_plugins.json" 2>/dev/null; then
    cl plugin update "$p@$MKT" >/dev/null 2>&1; print "   $p: al día"
  elif cl plugin install "$p@$MKT" >/dev/null 2>&1; then
    print "   $p: instalado"
  else
    print "   ❌ $p: no se pudo instalar"
  fi
done
if ! grep -q "\"creativos-base@$MKT\"" "$C/plugins/installed_plugins.json" 2>/dev/null; then
  print "   ❌ El plugin base no quedó instalado: no sigo. Instala el kit desde la app (INSTALAR.md)."
  exit 1
fi

# 4. Si quedó la versión 1: pasarla a la 2 (mueve, no borra; copia de settings.json antes)
say "3/4 · Versión 1"
py=""
dev=$(/usr/bin/xcode-select -p 2>/dev/null)
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/Current/bin/python3 "${dev:+$dev/usr/bin/python3}"; do
  [[ -n "$p" && -x "$p" ]] && "$p" -c 'import sys' >/dev/null 2>&1 && py="$p" && break
done
viejas=0
while read -r s p; do [[ -n "$s" && "$s" != \#* && -d "$C/skills/$s" ]] && (( viejas++ )); done < "$LISTA"
hooks1=0; grep -q 'skills/mdfilesummary/scripts/md_files.py' "$C/settings.json" 2>/dev/null && hooks1=1
if (( viejas == 0 && hooks1 == 0 )); then
  print "   no hay restos de la versión 1"
elif (( ! ACTUALIZAR )); then
  print "   Hay $viejas skills y hooks de la versión 1. Para pasarlos a la 2: zsh \"$0\" --actualizar"
  print "   (o dile a Claude: \"actualiza el kit\")."
elif [[ -z "$py" ]]; then
  print "   Hay restos de la versión 1, pero falta Python para moverlos. Dile a Claude: \"haz el chequeo\"."
else
  "$py" "$BASE_DIR/skills/actualizar-kit/scripts/migrar_v1.py" --aplicar | sed 's/^/   /'
fi

say "4/4 · Listo"
print "   Cierra Claude por completo (Cmd+Q) y vuelve a abrirlo: las sesiones abiertas no ven lo nuevo."
print "   Después dile a Claude: \"haz el chequeo\" (revisa programas, memoria y perfil, y arregla lo que falte)."
