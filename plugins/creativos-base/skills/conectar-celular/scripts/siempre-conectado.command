#!/bin/zsh
# Modo «siempre conectado» (Mac): la computadora se conecta sola con el celular cada vez que
# inicias sesión y se reconecta sola si se cae, sin pestaña de terminal abierta.
# PENDIENTE DE PRUEBA en una cuenta nueva de Mac (ver PRUEBAS-celular.md del taller).
#
# Uso:
#   zsh siempre-conectado.command                    instalar (carpeta ~/PROYECTOS)
#   zsh siempre-conectado.command instalar RUTA      instalar con otra carpeta
#   zsh siempre-conectado.command quitar             desinstalar (el registro queda)
#   zsh siempre-conectado.command --simular          mostrar lo que haría, sin tocar nada
#
# Antes hay que conectarlo UNA vez a mano (conectar-celular.command) en esa carpeta: sin
# terminal no se pueden responder «Enable Remote Control? (y/n)» ni «Trust …? [y/N]».

source "${0:A:h}/comun.sh" || { print "❌ Falta comun.sh al lado de este script."; exit 1; }

accion=instalar simular=0 CARPETA=""
for a in "$@"; do
  case $a in
    instalar|quitar) accion=$a ;;
    --simular) simular=1 ;;
    *) CARPETA=$a ;;
  esac
done
CARPETA=${${CARPETA:-$CARPETA_POR_DEFECTO}:A}
AGENTES=${CELULAR_AGENTES:-$HOME/Library/LaunchAgents}
PLIST=$AGENTES/$ETIQUETA.plist

if [[ $accion == quitar ]]; then
  if (( simular )); then
    print "[simular] launchctl bootout gui/$UID/$ETIQUETA y borrar $PLIST"
    exit 0
  fi
  launchctl bootout "gui/$UID/$ETIQUETA" 2>/dev/null
  rm -f "$PLIST"
  print "✅ Modo automático quitado. Desde ahora se conecta solo cuando lo pidas («conecta el celular»)."
  print "   El registro queda en $CELULAR_DIR/celular.log."
  exit 0
fi

print -P "%B📱  Dejar la computadora siempre conectada con el celular%b\n"

# 1. Claude Code y sesión iniciada
if ! bin=$(buscar_claude); then
  print "❌ No encontré Claude Code con Remote Control. Abre la app de Claude, entra una vez a la pestaña Code"
  print "   y vuelve a intentar."
  exit 1
fi
if ! who=$(cuenta "$bin"); then
  print "⚠️  Falta iniciar sesión en el Claude Code de la computadora. Primero conéctalo una vez con el"
  print "   comando de conectar (abre el navegador). Después vuelve a tocar este."
  exit 0
fi

# 2. Las dos preguntas de la primera vez, ya respondidas en esa carpeta
pv=$(primera_vez "$CARPETA")
if [[ $pv != "dialogo=true confianza=true" ]]; then
  print "⚠️  Antes de dejarlo automático, conéctalo UNA vez a mano en esa carpeta y responde y a las preguntas:"
  print "     zsh \"${0:A:h}/conectar-celular.command\" \"$CARPETA\""
  print "   Sin terminal no se pueden responder «Enable Remote Control?» ni «Trust …?», y no arrancaría."
  print "   ($pv)"
  exit 0
fi

# 3. Copia fija del arranque (la carpeta del plugin cambia con cada actualización del kit)
xml() { local s=${1//&/&amp;}; s=${s//</&lt;}; s=${s//>/&gt;}; print -r -- "$s"; }
LOG=$CELULAR_DIR/celular.log
contenido=$(cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ETIQUETA</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-l</string>
    <string>$(xml "$CELULAR_DIR/arrancar-servidor.sh")</string>
  </array>
  <key>WorkingDirectory</key><string>$(xml "$CARPETA")</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
  <key>StandardOutPath</key><string>$(xml "$LOG")</string>
  <key>StandardErrorPath</key><string>$(xml "$LOG")</string>
</dict>
</plist>
EOF
)

if (( simular )); then
  tmp=$(mktemp -t celular-plist) && print -r -- "$contenido" > "$tmp"
  if plutil -lint "$tmp" >/dev/null; then print "[simular] plist válido (plutil -lint)"; else print "[simular] ❌ plist inválido"; fi
  rm -f "$tmp"
  print "[simular] copiaría arrancar-servidor.sh, comun.sh y estado.sh a $CELULAR_DIR"
  print "[simular] escribiría $PLIST:"
  print -r -- "$contenido"
  print "[simular] launchctl bootstrap gui/$UID $PLIST"
  exit 0
fi

mkdir -p "$CELULAR_DIR" "$AGENTES"
cp -f "${0:A:h}/arrancar-servidor.sh" "${0:A:h}/comun.sh" "${0:A:h}/estado.sh" "$CELULAR_DIR/" || {
  print "❌ No pude copiar el arranque a $CELULAR_DIR."; exit 1; }
chmod 755 "$CELULAR_DIR/arrancar-servidor.sh" "$CELULAR_DIR/estado.sh"
print -r -- "$CARPETA" > "$CELULAR_DIR/carpeta.txt"
print -r -- "$contenido" > "$PLIST"
if ! plutil -lint "$PLIST" >/dev/null; then
  print "❌ El archivo del agente salió mal ($PLIST). No se instaló nada."
  rm -f "$PLIST"; exit 1
fi

# 4. Cargarlo (si ya estaba, se recarga con la versión nueva)
launchctl bootout "gui/$UID/$ETIQUETA" 2>/dev/null
if ! launchctl bootstrap "gui/$UID" "$PLIST"; then
  print "❌ macOS no dejó cargar el agente. Nada quedó corriendo; se puede seguir con la pestaña de la terminal."
  exit 1
fi

print "✅ Instalado. Desde ahora se conecta sola al iniciar sesión y se reconecta si se cae."
print "   • macOS puede avisar «Se añadió un elemento en segundo plano» (zsh o claude): es esto. Déjalo activado."
print "   • Si tienes abierta una pestaña donde dice «Connected», ciérrala (Control+C): el automático la"
print "     reemplaza en menos de un minuto."
print "   • La primera vez que desde el celular pidas algo de Escritorio, Documentos, Descargas o un disco,"
print "     macOS pregunta en la computadora: hazlo hoy con la compu al lado y toca «Permitir»."
print "   • Para quitarlo: «quita el modo siempre conectado»."
print
zsh "${0:A:h}/estado.sh" --esperar 60
