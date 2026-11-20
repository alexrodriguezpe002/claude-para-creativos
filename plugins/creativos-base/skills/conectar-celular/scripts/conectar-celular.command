#!/bin/zsh
# Conecta esta computadora con la app de Claude del celular (Remote Control): aparece en la
# pestaña Código del celular y las sesiones que se abren desde ahí corren acá, con tus archivos,
# tus skills y tu memoria. Corre en una pestaña de la terminal de la app de Claude y funciona
# mientras esa pestaña esté abierta. Si se corta (internet, la compu se durmió, se actualizó
# Claude), vuelve a conectar solo.
#
# Uso:  zsh conectar-celular.command [carpeta]      (por defecto ~/PROYECTOS)

source "${0:A:h}/comun.sh" || { print "❌ Falta comun.sh al lado de este script."; exit 1; }

ESPERA=${CELULAR_ESPERA:-30}          # segundos antes de reconectar
CARPETA=${${1:-$CARPETA_POR_DEFECTO}:A}

[[ -t 1 ]] && clear
print -P "%B📱  Conectar esta computadora con Claude en el celular%b\n"

# 0. Si ya hay una conexión abierta, no se abre otra. La segunda falla («already served»),
#    repite «Se cortó» cada 30 segundos y parece que nada funciona, cuando la primera sí anda.
if ya=$(servidores | head -1) && [[ -n $ya ]]; then
  read -r pid ppid secs dir <<< "$ya"
  print "✅ Ya está conectada (hace $(duracion $secs), en la carpeta ${dir:-?}). No hace falta nada más."
  print "   Esta pestaña ya se puede cerrar: la conexión sigue donde se abrió."
  exit 0
fi

# 1. El Claude Code más nuevo con Remote Control (el `claude` de la Terminal puede ser viejo)
if ! bin=$(buscar_claude); then
  print "❌ No encontré Claude Code con Remote Control en esta computadora."
  print "   Abre la app de Claude, entra una vez a la pestaña Code y vuelve a tocar ▷."
  exit 1
fi

# 2. Sesión iniciada en el Claude Code de la computadora (una sola vez)
if ! who=$(cuenta "$bin"); then
  print -P "%BPaso 1 · Iniciar sesión%b"
  print "Se abre el navegador: entra con tu cuenta de Claude (la misma del celular) y toca «Authorize»."
  until who=$(cuenta "$bin"); do
    env_limpio "$bin" auth login --claudeai
    who=$(cuenta "$bin") && break
    print; read -r "?No se completó. Aprieta Enter para intentar de nuevo… "
  done
fi
print "✅ Sesión iniciada: $who\n"

# 3. La carpeta donde empiezan las sesiones que abras desde el celular. Nunca la carpeta de inicio:
#    ahí pregunta «Trust …?» cada vez que arranca (ver comun.sh).
if ! { mkdir -p "$CARPETA" && cd "$CARPETA"; }; then
  print "❌ No pude abrir la carpeta $CARPETA."
  exit 1
fi

# 4. Que macOS pida los permisos ahora, contigo frente a la compu, y no después con la compu sola.
#    Si ya se conectó antes (las dos preguntas respondidas), no se muestran los pasos: solo «Conectando…».
pv=$(primera_vez "$CARPETA")
nueva=1; [[ $pv == "dialogo=true confianza=true" ]] && nueva=0
if (( nueva )); then
  print -P "%BPaso 2 · Permisos de macOS%b"
  print "Si macOS pregunta si «Claude» (o «Terminal») puede acceder a una carpeta o a un disco,"
  print "toca «Permitir». Así después, desde el celular, no se traba nada.\n"
fi
red=(${(f)"$(mount 2>/dev/null | awk '/\((smbfs|afpfs|nfs|webdav)/ {print $3}')"})
for d in /Volumes/*(N/) "$HOME/Desktop" "$HOME/Documents" "$HOME/Downloads"; do
  [[ $d == /Volumes/Recovery ]] && continue
  (( ${red[(Ie)$d]} )) && continue          # un disco de red desconectado puede colgar el ls
  ls "$d" >/dev/null 2>&1
done

# 5. Conectar. --spawn=same-dir evita una pregunta más en carpetas con git.
spawn=()
"$bin" remote-control --help 2>/dev/null | grep -q -- '--spawn' && spawn=(--spawn=same-dir)
if (( nueva )); then
  print -P "%BPaso 3 · Conectar%b"
  print "Solo esta vez puede preguntar esto. Escribe y y aprieta Enter:"
  [[ $pv == *"dialogo=true"* ]] || print "  • «Enable Remote Control? (y/n)»   (¿activar el control desde el celular?)"
  [[ $pv == *"confianza=true"* ]] || print "  • «Trust $CARPETA? [y/N]»   (¿confías en esta carpeta?)"
  print "Cuando diga «Connected», ya está. Deja esta pestaña abierta; la app de Claude puede quedar minimizada."
  maquina=$(scutil --get LocalHostName 2>/dev/null)
  print "En el celular: pestaña Código › «${maquina:-tu compu}» › al abrir una sesión, elige «${CARPETA:t}»."
else
  print "Conectando… Cuando diga «Connected», ya está. Deja esta pestaña abierta."
fi
print "Para desconectar: haz clic dentro de esta pestaña y aprieta control + C (la tecla ⌃ control, no ⌘ cmd),"
print "o cierra la pestaña.\n"
trap 'print "\nDesconectado. Ya puedes cerrar esta pestaña."; exit 0' INT TERM

seguidas=0
while true; do
  inicio=$SECONDS
  # caffeinate -s: enchufada, la compu no se duerme mientras está conectada (con batería sí puede)
  env_limpio /usr/bin/caffeinate -s "$bin" remote-control "${spawn[@]}"
  codigo=$?
  (( codigo == 0 )) && break

  # ¿Otra pestaña o el modo automático tomó la conexión? Entonces esta sobra.
  if ya=$(servidores | head -1) && [[ -n $ya ]]; then
    print "\n✅ Ya hay otra conexión abierta (otra pestaña o el modo automático). Esta pestaña ya se puede cerrar."
    exit 0
  fi
  # ¿Se cerró la sesión de Claude? Volver a entrar.
  if ! cuenta "$bin" >/dev/null; then
    print "\nSe cerró la sesión de Claude en la computadora. Se abre el navegador para entrar de nuevo…"
    env_limpio "$bin" auth login --claudeai
  fi
  if (( SECONDS - inicio < 20 )); then (( seguidas++ )); else seguidas=0; fi
  if (( seguidas >= 5 )); then
    print "\n❌ No logra conectar (5 intentos seguidos). El mensaje de arriba dice por qué."
    print "   Pídele a Claude «no conecta el celular» y pásale ese mensaje."
    read -r "?Aprieta Enter para intentar de nuevo… "
    seguidas=0
  else
    print "\n🔄 Se cortó la conexión (sin internet, la compu se durmió o se actualizó Claude)."
    print "   Vuelvo a conectar solo en $ESPERA segundos. No tienes que hacer nada."
    sleep $ESPERA
  fi
  nuevo=$(buscar_claude) && bin=$nuevo   # por si la app se actualizó y la versión vieja ya no está
done
print "\nDesconectado. Ya puedes cerrar esta pestaña."
