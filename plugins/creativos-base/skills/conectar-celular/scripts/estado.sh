#!/bin/zsh
# ¿Está conectado el celular con esta Mac? (Remote Control)
#
# NUNCA termina con error: el código de salida es siempre 0, así la app no lo muestra como
# «Failed» cuando la respuesta es «no conectada» (pgrep sí sale con 1 y por eso parecía una falla).
# La primera línea es el estado, para que Claude la lea:
#   ESTADO: conectada | conectando | no conectada | duplicada
# Uso:
#   zsh estado.sh                     cómo está ahora
#   zsh estado.sh --esperar 40        después de tocar ▷: espera hasta 40 s a que conecte
#   zsh estado.sh --carpeta RUTA      solo el servidor que trabaja en esa carpeta

source "${0:A:h}/comun.sh" 2>/dev/null || {
  print "ESTADO: desconocido"
  print "No encontré comun.sh al lado de este script (${0:A:h})."
  exit 0
}

esperar=0 carpeta=""
while (( $# )); do
  case $1 in
    --esperar) esperar=${2:-40}; shift; (( $# )) && shift ;;
    --carpeta) carpeta=${2:A};   shift; (( $# )) && shift ;;
    *) shift ;;
  esac
done
[[ $esperar == <-> ]] || esperar=40

ESTADO="" DETALLE=()

evaluar() {
  local l pid ppid secs dir est mejor_est=-1 mejor="" n_carpeta i
  local -a lista
  local -A por_carpeta
  ESTADO="" DETALLE=()
  lista=("${(@f)$(servidores "$carpeta")}")
  lista=(${lista:#})
  if (( ${#lista} == 0 )); then
    ESTADO="no conectada"
    return
  fi
  for l in $lista; do
    read -r pid ppid secs dir <<< "$l"
    por_carpeta[${dir:-?}]=$(( ${por_carpeta[${dir:-?}]:-0} + 1 ))
    est=$(conexiones "$pid")
    if (( est == 0 && secs >= 8 )); then   # un hueco momentáneo entre consultas no es «sin internet»
      for i in 1 2 3; do sleep 0.5; est=$(conexiones "$pid"); (( est > 0 )) && break; done
    fi
    # el mejor: el que ya habla con internet; si ninguno, el más viejo
    if (( est > 0 && secs >= 8 )); then
      if (( mejor_est <= 0 )); then mejor=$l; mejor_est=$est; fi
    elif [[ -z $mejor ]]; then
      mejor=$l; mejor_est=0
    fi
  done
  read -r pid ppid secs dir <<< "$mejor"
  local modo modo_corto sesiones
  if (( ppid == 1 )); then
    modo="en modo automático (arranca solo al iniciar sesión)"; modo_corto="modo automático"
  else
    modo="en una pestaña de la terminal (se corta si cierras la app de Claude o esa pestaña)"
    modo_corto="en una pestaña de la terminal"
  fi
  sesiones=$(pgrep -P "$pid" -x claude 2>/dev/null | wc -l | tr -d ' ')

  if (( mejor_est > 0 && secs >= 8 )); then
    ESTADO="conectada"
    DETALLE+=("✅ El celular ya puede usar esta computadora.")
    DETALLE+=("   Conectada hace $(duracion $secs), $modo.")
    DETALLE+=("   Carpeta donde empiezan las sesiones nuevas: ${dir:-?}")
    DETALLE+=("   En el celular: pestaña Código › «$(scutil --get LocalHostName 2>/dev/null || hostname -s)» › al abrir una sesión, «${${dir:-?}:t}».")
    DETALLE+=("   Sesiones abiertas desde el celular o la web ahora: $sesiones")
  elif (( secs < 8 )); then
    ESTADO="conectando"
    DETALLE+=("⏳ Arrancó hace $(duracion $secs) y todavía está conectando. Mirar de nuevo en unos segundos (--esperar 30).")
  else
    ESTADO="conectando"
    DETALLE+=("⏳ Hay un servidor abierto hace $(duracion $secs), $modo_corto, pero todavía no habla con Claude en internet.")
    if (( ppid == 1 )); then
      local diag=$(diagnostico_registro)
      [[ -n $diag ]] && DETALLE+=("   Registro: $diag")
    else
      DETALLE+=("   Casi siempre está esperando una respuesta en esa pestaña de la terminal: «Enable Remote Control? (y/n)»,")
      DETALLE+=("   «Trust …? [y/N]» (escribir y + Enter) o iniciar sesión en el navegador. Si no, falta internet.")
      DETALLE+=("   Para verlo: leer la pestaña con read_terminal.")
    fi
  fi

  # más de un servidor en la misma carpeta: el segundo falla («already served») y parece un error
  for dir n_carpeta in "${(@kv)por_carpeta}"; do
    if (( n_carpeta > 1 )); then
      [[ $ESTADO == conectada ]] || ESTADO="duplicada"
      DETALLE+=("⚠️  Hay $n_carpeta servidores en la misma carpeta (${dir:-?}).")
      if [[ $ESTADO == conectada ]]; then
        DETALLE+=("   Sobra uno: cerrar la pestaña que repite «Se cortó» (clic dentro y ⌃ control + C). La que dice Connected sigue funcionando.")
      else
        DETALLE+=("   Sobra uno: cerrar (clic dentro y ⌃ control + C) todas las pestañas de conectar menos una, y mirar de nuevo.")
      fi
    fi
  done
  (( ${#lista} > 1 )) && DETALLE+=("   (Servidores abiertos: ${#lista}.)")
}

evaluar
if (( esperar > 0 )) && [[ $ESTADO != conectada ]]; then
  inicio=$SECONDS
  while (( SECONDS - inicio < esperar )); do
    sleep 2
    evaluar
    [[ $ESTADO == conectada ]] && break
  done
  DETALLE+=("   (Esperé $(( SECONDS - inicio )) s.)")
fi

print "ESTADO: $ESTADO"
if [[ $ESTADO == "no conectada" ]]; then
  if agente_cargado; then
    print "❌ El modo automático está instalado pero no hay ningún servidor corriendo ahora."
    diag=$(diagnostico_registro)
    [[ -n $diag ]] && print "   Registro: $diag"
    print "   Registro completo: $CELULAR_DIR/celular.log"
  else
    print "❌ No hay ninguna conexión abierta: el celular no puede abrir sesiones nuevas en esta computadora."
    print "   Se conecta tocando ▷ en el comando de conectar (o, si se instaló, con el modo automático)."
  fi
else
  print -l -- $DETALLE
fi
agente_cargado && [[ $ESTADO != "no conectada" ]] && print "   Modo automático: instalado."
exit 0
