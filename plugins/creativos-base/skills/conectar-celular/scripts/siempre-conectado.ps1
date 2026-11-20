# Modo «siempre conectado» (Windows): la computadora se conecta sola con el celular al iniciar
# sesión y se reconecta si se cae, sin ventana abierta.
# Uso:
#   powershell -NoProfile -ExecutionPolicy Bypass -File siempre-conectado.ps1                 instalar
#   powershell -NoProfile -ExecutionPolicy Bypass -File siempre-conectado.ps1 -Accion quitar  desinstalar
#   ... -Simular                                                                              mostrar sin tocar nada
# Antes hay que conectarlo UNA vez a mano (conectar-celular.ps1) en esa carpeta.
# PENDIENTE DE PRUEBA en una PC con Windows.
param([string]$Accion = 'instalar', [string]$Carpeta = '', [switch]$Simular)

. (Join-Path $PSScriptRoot 'comun.ps1')
if (-not $Carpeta) { $Carpeta = $CarpetaPorDefecto }
$inicioVbs = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\claude-conectar-celular.vbs'

if ($Accion -eq 'quitar') {
  if ($Simular) { Write-Output "[simular] quitaría la tarea «$NombreTarea» y $inicioVbs"; exit 0 }
  Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:$false -ErrorAction SilentlyContinue
  Remove-Item -Force -ErrorAction SilentlyContinue $inicioVbs
  Write-Output '✅ Modo automático quitado. Desde ahora se conecta solo cuando lo pidas («conecta el celular»).'
  Write-Output '   Si quedó un servidor corriendo, se cierra al cerrar sesión o reiniciar.'
  exit 0
}

Write-Output "Dejar la computadora siempre conectada con el celular`n"
$bin = Find-Claude
if (-not $bin) { Write-Output '❌ No encontré Claude Code con Remote Control. Abre la app de Claude y entra una vez a la pestaña Code.'; exit 1 }
if (-not (Get-Cuenta $bin)) {
  Write-Output '⚠️  Falta iniciar sesión. Primero conéctalo una vez con el comando de conectar (abre el navegador).'
  exit 0
}
$pv = Get-PrimeraVez $Carpeta
if (-not ($pv.Dialogo -and $pv.Confianza)) {
  Write-Output '⚠️  Antes de dejarlo automático, conéctalo UNA vez a mano en esa carpeta y responde y a las preguntas:'
  Write-Output ('     powershell -NoProfile -ExecutionPolicy Bypass -File "{0}" -Carpeta "{1}"' -f (Join-Path $PSScriptRoot 'conectar-celular.ps1'), $Carpeta)
  Write-Output ('   (dialogo={0} confianza={1})' -f $pv.Dialogo, $pv.Confianza)
  exit 0
}

$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arranque = Join-Path $CelularDir 'arrancar-servidor.ps1'
$argumentos = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$arranque`""
if ($Simular) {
  Write-Output "[simular] copiaría comun.ps1, arrancar-servidor.ps1 y estado.ps1 a $CelularDir"
  Write-Output "[simular] registraría la tarea «$NombreTarea» al iniciar sesión: $ps $argumentos"
  exit 0
}

New-Item -ItemType Directory -Force -Path $CelularDir | Out-Null
foreach ($f in 'comun.ps1', 'arrancar-servidor.ps1', 'estado.ps1') { Copy-Item -Force (Join-Path $PSScriptRoot $f) $CelularDir }
Set-Content -Path (Join-Path $CelularDir 'carpeta.txt') -Value $Carpeta -Encoding UTF8

$ok = $false
try {
  $a = New-ScheduledTaskAction -Execute $ps -Argument $argumentos
  $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
  Register-ScheduledTask -TaskName $NombreTarea -Action $a -Trigger $t -Settings $s `
    -Description 'Conecta esta computadora con Claude en el celular (kit creativos)' -Force -ErrorAction Stop | Out-Null
  Start-ScheduledTask -TaskName $NombreTarea -ErrorAction Stop
  $ok = $true
  Write-Output '✅ Instalado en el Programador de tareas: se conecta sola al iniciar sesión.'
} catch {
  # sin permiso para tareas: acceso oculto en la carpeta Inicio
  try {
    New-Item -ItemType Directory -Force -Path (Split-Path $inicioVbs) | Out-Null
    $linea = 'CreateObject("Wscript.Shell").Run """' + $ps + '"" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""' + $arranque + '""", 0, False'
    Set-Content -Path $inicioVbs -Value $linea -Encoding ASCII
    Start-Process -FilePath 'wscript.exe' -ArgumentList "`"$inicioVbs`""
    $ok = $true
    Write-Output '✅ Instalado en la carpeta Inicio (Windows no dejó crear la tarea): se conecta sola al iniciar sesión.'
  } catch {
    Write-Output ("❌ No se pudo instalar: {0}. Se puede seguir con la ventana de la terminal." -f $_.Exception.Message)
  }
}
if ($ok) {
  Write-Output '   • Si tienes abierta una ventana donde dice «Connected», ciérrala: el automático la reemplaza en un minuto.'
  Write-Output '   • Para quitarlo: «quita el modo siempre conectado».'
  & (Join-Path $PSScriptRoot 'estado.ps1') -Esperar 60
}
exit 0
