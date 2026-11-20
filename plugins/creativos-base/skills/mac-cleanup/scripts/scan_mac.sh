#!/bin/bash
# scan_mac.sh — Inventario de basura en el disco interno. NO BORRA NADA.
# Salida: reporte humano + TSV en $OUT/tier1.tsv y $OUT/tier2.tsv
set -uo pipefail
OUT="${1:?uso: scan_mac.sh <dir-de-salida>}"
mkdir -p "$OUT" || exit 2
: > "$OUT/tier1.tsv"; : > "$OUT/tier2.tsv"; : > "$OUT/blocked.txt"

PROTECTED="POWER BINS|POWERGRADES|ENCODER PRESET|Motion Graphics Templates|Adobe/Common/Plug-ins|/.claude/skills|/.claude/plugins|/.agents/skills|/.claude/projects/.*/memory"
kb () { du -sk "$1" 2>/dev/null | cut -f1; }
protected () { echo "$1" | grep -qE "$PROTECTED"; }
add () { # add <tier-file> <etiqueta> <ruta>
  [ -e "$3" ] || return 0
  protected "$3" && return 0
  grep -qF "	$3" "$OUT/tier1.tsv" "$OUT/tier2.tsv" 2>/dev/null && return 0
  local k; k=$(kb "$3"); [ -z "$k" ] && return 0
  [ "$k" -lt 10240 ] && return 0          # ignorar < 10 MB
  printf '%s\t%s\t%s\n' "$k" "$2" "$3" >> "$1"
}

echo "== ESPACIO ANTES =="
df -h / | tail -1 | awk '{print "  libre: "$4"  de "$2"  ("$5" usado)"}'
FREE0=$(df -k / | tail -1 | awk '{print $4}')
echo "$FREE0" > "$OUT/free_before"

# ---------------------------------------------------------------- apps abiertas
echo; echo "== APPS DE ADOBE ABIERTAS =="
ADOBE_RUNNING=0
if pgrep -f "Adobe Premiere Pro|Adobe After Effects|Adobe Media Encoder|Adobe Audition" >/dev/null 2>&1; then
  ADOBE_RUNNING=1
  pgrep -fl "Adobe Premiere Pro|Adobe After Effects|Adobe Media Encoder|Adobe Audition" 2>/dev/null \
    | sed 's|.*/||' | sort -u | sed 's/^/  ABIERTA: /'
  echo "  -> la Media Cache compartida queda BLOQUEADA" | tee -a "$OUT/blocked.txt"
else
  echo "  ninguna — se puede tocar la Media Cache"
fi
echo "$ADOBE_RUNNING" > "$OUT/adobe_running"

# ------------------------------------------- cachés de versiones desinstaladas
# Regla: Adobe <App> 20XX  ->  carpeta de caché "XX."  (2026 -> 26.)
echo; echo "== CACHES DE ADOBE DE VERSIONES QUE YA NO ESTAN INSTALADAS =="
for APP in "After Effects" "Premiere Pro" "Audition" "Media Encoder"; do
  CDIR="$HOME/Library/Caches/Adobe/$APP"
  [ -d "$CDIR" ] || continue
  KEEP=$(ls /Applications 2>/dev/null | grep -i "Adobe $APP 20" \
         | sed -E 's/.*20([0-9]{2}).*/\1./' | sort -u)
  for v in "$CDIR"/*/; do
    [ -d "$v" ] || continue
    vn=$(basename "$v")
    if [ -n "$KEEP" ] && echo "$KEEP" | grep -q "^${vn%%.*}\.$"; then
      echo "  CONSERVAR  $APP $vn (instalada)"
    else
      echo "  HUERFANA   $APP $vn  ->  $(du -sh "$v" 2>/dev/null | cut -f1)"
      add "$OUT/tier1.tsv" "cache AE/PR huerfana ($APP $vn)" "$v"
    fi
  done
done

# ------------------------------------------------------- whisper: cuál se usa
echo; echo "== MODELOS DE TRANSCRIPCION =="
USED=$(grep -rhoE "hyperframes transcribe|whisper\.cpp|faster.whisper|faster_whisper|import whisper|openai-whisper" \
       "$HOME/.claude/skills" "$HOME/.claude/plugins" "$HOME/.agents/skills" 2>/dev/null | sort -u | tr '\n' ' ')
echo "  referencias en las skills: ${USED:-ninguna}"
declare -a WMAP=(
  "$HOME/.cache/hyperframes/whisper|hyperframes transcribe"
  "$HOME/.cache/huggingface|faster.whisper|faster_whisper|WhisperModel"
  "$HOME/.cache/whisper|import whisper|whisper --model|openai-whisper"
)
for row in "${WMAP[@]}"; do
  P="${row%%|*}"; PATTERNS="${row#*|}"
  [ -d "$P" ] || continue
  N=0
  IFS='|' read -ra PAT <<< "$PATTERNS"
  for pat in "${PAT[@]}"; do
    c=$(grep -rlE "$pat" "$HOME/.claude/skills" "$HOME/.claude/plugins" "$HOME/.agents/skills" 2>/dev/null | wc -l | tr -d ' ')
    N=$((N+c))
  done
  SZ=$(du -sh "$P" 2>/dev/null | cut -f1)
  if [ "$N" -gt 0 ]; then
    echo "  EN USO ($N skills)  $P  ($SZ)  -> CONSERVAR"
  else
    echo "  SIN REFERENCIAS     $P  ($SZ)  -> candidato, PREGUNTAR (re-descarga lenta)"
    add "$OUT/tier2.tsv" "modelos whisper sin referencias en skills" "$P"
  fi
done

# ----------------------------------------------------------- TIER 1 regenerable
echo; echo "== TIER 1 — REGENERABLE, BORRADO AUTOMATICO =="
add "$OUT/tier1.tsv" "npm _npx"                 "$HOME/.npm/_npx"
add "$OUT/tier1.tsv" "npm _cacache"             "$HOME/.npm/_cacache"
add "$OUT/tier1.tsv" "cache Camera Raw"         "$HOME/Library/Caches/Adobe Camera Raw 2"
add "$OUT/tier1.tsv" "cache CSXS (Adobe)"       "$HOME/Library/Caches/CSXS"
add "$OUT/tier1.tsv" "logs Creative Cloud"      "$HOME/Library/Logs/CreativeCloud"
add "$OUT/tier1.tsv" "logs Adobe"               "$HOME/Library/Logs/Adobe"
add "$OUT/tier1.tsv" "cache CapCut"             "$HOME/Movies/CapCut/User Data/Cache"
add "$OUT/tier1.tsv" "cache Spotify"            "$HOME/Library/Caches/com.spotify.client"
add "$OUT/tier1.tsv" "cache Google/Chrome"      "$HOME/Library/Caches/Google"
add "$OUT/tier1.tsv" "cache Homebrew"           "$HOME/Library/Caches/Homebrew"
add "$OUT/tier1.tsv" "cache pip"                "$HOME/Library/Caches/pip"
add "$OUT/tier1.tsv" "cache Google DriveFS"     "$HOME/Library/Application Support/Google/DriveFS"
add "$OUT/tier1.tsv" "updater Loom"             "$HOME/Library/Caches/com.loom.desktop.ShipIt"
add "$OUT/tier1.tsv" "cache notion-updater"     "$HOME/Library/Caches/notion-updater"
# Media cache compartida de Adobe — solo si no hay apps abiertas
if [ "$ADOBE_RUNNING" = 0 ]; then
  for f in "Media Cache Files" "Media Cache" "Peak Files" "Analyzer Cache Files" "Metadata Cache"; do
    add "$OUT/tier1.tsv" "Adobe Common / $f" "$HOME/Library/Application Support/Adobe/Common/$f"
  done
else
  echo "  (Media Cache omitida: hay apps de Adobe abiertas)"
fi
# Temporales de Claude, solo los de más de 1 día
find /private/tmp/claude-501 -maxdepth 1 -mindepth 1 -mtime +1 \
     \( -name "bash-edit-diff" -o -name "cache-break-state-*.json" \) 2>/dev/null \
     | while IFS= read -r p; do add "$OUT/tier1.tsv" "temporal de Claude" "$p"; done
find /private/tmp/claude-501/*/ -maxdepth 1 -mindepth 1 -type d -mtime +1 2>/dev/null \
     | while IFS= read -r p; do add "$OUT/tier1.tsv" "scratchpad de sesion vieja" "$p"; done
# Barrido genérico: cualquier otra caché grande que no esté en la lista
du -d 1 -k "$HOME/Library/Caches" 2>/dev/null | awk '$1>512000' | sort -rn | tail -n +2 \
  | while IFS=$'\t' read -r k p; do grep -qF "$p" "$OUT/tier1.tsv" 2>/dev/null || \
      printf '%s\tcache grande sin clasificar\t%s\n' "$k" "$p" >> "$OUT/tier2.tsv"; done

sort -rn -o "$OUT/tier1.tsv" "$OUT/tier1.tsv"
awk -F'\t' '{printf "  %8.2f GB  %s\n", $1/1048576, $2}' "$OUT/tier1.tsv"
awk -F'\t' '{s+=$1} END {printf "  ---------------------\n  TOTAL TIER 1: %.2f GB en %d items\n", s/1048576, NR}' "$OUT/tier1.tsv"

# --------------------------------------------------------------- TIER 2 opinable
echo; echo "== TIER 2 — HAY QUE PREGUNTAR =="
add "$OUT/tier2.tsv" "historial de sesiones de Claude" "$HOME/.claude/projects"
add "$OUT/tier2.tsv" "backups de proyectos Resolve"    "$HOME/Movies/Resolve Project Backups"
add "$OUT/tier2.tsv" "navegador de Playwright"         "$HOME/Library/Caches/ms-playwright"
add "$OUT/tier2.tsv" "navegador de Puppeteer"          "$HOME/.cache/puppeteer"
add "$OUT/tier2.tsv" "navegador de HyperFrames"        "$HOME/.cache/hyperframes/chrome"
for d in "$HOME/Downloads" "$HOME/Desktop"; do
  find "$d" -maxdepth 1 -mindepth 1 -mtime +180 2>/dev/null | while IFS= read -r p; do
    add "$OUT/tier2.tsv" "VIEJO (informativo, no propuesta)" "$p"; done
done
sort -rn -o "$OUT/tier2.tsv" "$OUT/tier2.tsv"
awk -F'\t' '{printf "  %8.2f GB  %-38s %s\n", $1/1048576, $2, $3}' "$OUT/tier2.tsv"
awk -F'\t' '{s+=$1} END {printf "  ---------------------\n  TOTAL TIER 2: %.2f GB en %d items\n", s/1048576, NR}' "$OUT/tier2.tsv"

echo; echo "== LEIDO =="
echo "  tier1: $(wc -l < "$OUT/tier1.tsv" | tr -d ' ') items | tier2: $(wc -l < "$OUT/tier2.tsv" | tr -d ' ') items"
[ ! -s "$OUT/tier1.tsv" ] && [ ! -s "$OUT/tier2.tsv" ] && { echo "  ERROR: cero items leidos, el escaneo no sirvio"; exit 2; }
exit 0
