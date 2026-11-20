#!/bin/bash
# clean_mac.sh — Borra lo que scan_mac.sh listó. Verifica de nuevo antes de tocar nada.
# uso: clean_mac.sh <dir-del-scan> <tier1|lista> [archivo-con-rutas]
set -uo pipefail
OUT="${1:?uso: clean_mac.sh <dir-del-scan> <tier1|lista> [archivo]}"
MODE="${2:?falta el modo: tier1 | lista}"
LIST="${3:-}"

case "$MODE" in
  tier1) SRC="$OUT/tier1.tsv"; [ -s "$SRC" ] || { echo "ERROR: $SRC vacio, nada que borrar"; exit 2; } ;;
  lista) SRC="${LIST:?falta el archivo de rutas}"; [ -s "$SRC" ] || { echo "ERROR: lista vacia"; exit 2; } ;;
  *) echo "ERROR: modo invalido"; exit 2 ;;
esac

# --- re-verificacion: nunca tocar la Media Cache con Adobe abierto -------------
ADOBE=0
pgrep -f "Adobe Premiere Pro|Adobe After Effects|Adobe Media Encoder|Adobe Audition" >/dev/null 2>&1 && ADOBE=1

FREE0=$(df -k / | tail -1 | awk '{print $4}')
echo "libre antes: $(echo "scale=1; $FREE0/1048576" | bc) GB"; echo

BORRADOS=0; SALTADOS=0
while IFS=$'\t' read -r a b c; do
  # tier1.tsv = <kb>\t<etiqueta>\t<ruta> ; lista = <ruta> sola
  if [ -n "${c:-}" ]; then P="$c"; L="$b"; else P="$a"; L="item"; fi
  [ -e "$P" ] || continue

  if echo "$P" | grep -q "Adobe/Common"; then
    if [ "$ADOBE" = 1 ]; then
      echo "  SALTADO  $L — hay una app de Adobe abierta"; SALTADOS=$((SALTADOS+1)); continue
    fi
    find "$P" -mindepth 1 -delete 2>/dev/null
    echo "  vaciado  $L (la carpeta se conserva, Adobe la necesita)"
  else
    rm -rf "$P" 2>/dev/null
    echo "  borrado  $L"
  fi
  BORRADOS=$((BORRADOS+1))
done < "$SRC"

sync
FREE1=$(df -k / | tail -1 | awk '{print $4}')
echo
echo "libre despues: $(echo "scale=1; $FREE1/1048576" | bc) GB"
echo "LIBERADO:      $(echo "scale=2; ($FREE1-$FREE0)/1048576" | bc) GB"
echo "items: $BORRADOS borrados, $SALTADOS saltados"
[ "$SALTADOS" -gt 0 ] && echo "NOTA: cerra las apps de Adobe y volve a correr para recuperar lo saltado"
exit 0
