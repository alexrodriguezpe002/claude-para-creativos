# ¿Está conectado el celular con esta computadora? (Remote Control) - Windows
# NUNCA termina con error: siempre sale con 0 y la primera línea dice el estado:
#   ESTADO: conectada | conectando | no conectada | duplicada
# Uso:
#   powershell -NoProfile -ExecutionPolicy Bypass -File estado.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File estado.ps1 -Esperar 40
# PENDIENTE DE PRUEBA en una PC con Windows.
param([int]$Esperar = 0)

try {
  . (Join-Path $PSScriptRoot 'comun.ps1')
} catch {
  Write-Output 'ESTADO: desconocido'
  Write-Output "No pude cargar comun.ps1 ($PSScriptRoot)."
  exit 0
}

function Get-Estado {
  $lista = @(Get-Servidores)
  $r = [pscustomobject]@{ Estado = 'no conectada'; Detalle = @() }
  if ($lista.Count -eq 0) { return $r }
  $mejor = $null; $mejorEst = -1
  foreach ($s in $lista) {
    $est = Get-Conexiones $s.Pid
    if ($est -eq 0 -and $s.Segundos -ge 8) {   # un hueco momentáneo entre consultas no es «sin internet»
      for ($i = 0; ($i -lt 3) -and ($est -eq 0); $i++) { Start-Sleep -Milliseconds 500; $est = Get-Conexiones $s.Pid }
    }
    if ($est -gt 0 -and $s.Segundos -ge 8) { if ($mejorEst -le 0) { $mejor = $s; $mejorEst = $est } }
    elseif (-not $mejor) { $mejor = $s; $mejorEst = 0 }
  }
  $auto = Test-TareaInstalada
  $modo = if ($auto) { 'modo automático o ventana de terminal' } else { 'en una ventana de terminal (se corta si la cierras)' }
  if ($mejorEst -gt 0 -and $mejor.Segundos -ge 8) {
    $r.Estado = 'conectada'
    $r.Detalle += '✅ El celular ya puede usar esta computadora.'
    $r.Detalle += ('   Conectada hace {0}, {1}.' -f (Format-Duracion $mejor.Segundos), $modo)
    $r.Detalle += ('   En el celular: pestaña Código › «{0}».' -f $env:COMPUTERNAME)
  } elseif ($mejor.Segundos -lt 8) {
    $r.Estado = 'conectando'
    $r.Detalle += ('⏳ Arrancó hace {0} y todavía está conectando. Mirar de nuevo en unos segundos (-Esperar 30).' -f (Format-Duracion $mejor.Segundos))
  } else {
    $r.Estado = 'conectando'
    $r.Detalle += ('⏳ Hay un servidor abierto hace {0}, pero todavía no habla con Claude en internet.' -f (Format-Duracion $mejor.Segundos))
    $r.Detalle += '   Casi siempre está esperando una respuesta en la ventana de la terminal: «Enable Remote Control? (y/n)»,'
    $r.Detalle += '   «Trust ...? [y/N]» (escribir y + Enter) o iniciar sesión en el navegador. Si no, falta internet.'
    $d = Get-DiagnosticoRegistro
    if ($d) { $r.Detalle += "   Registro: $d" }
  }
  if ($lista.Count -gt 1) {
    if ($r.Estado -ne 'conectada') { $r.Estado = 'duplicada' }
    $r.Detalle += ('⚠️  Hay {0} servidores abiertos. Sobra uno: cerrar la ventana que repite «Se cortó» (Control+C).' -f $lista.Count)
  }
  return $r
}

$e = Get-Estado
if ($Esperar -gt 0 -and $e.Estado -ne 'conectada') {
  $inicio = Get-Date
  while (((Get-Date) - $inicio).TotalSeconds -lt $Esperar) {
    Start-Sleep -Seconds 2
    $e = Get-Estado
    if ($e.Estado -eq 'conectada') { break }
  }
  $e.Detalle += ('   (Esperé {0} s.)' -f [int]((Get-Date) - $inicio).TotalSeconds)
}

Write-Output "ESTADO: $($e.Estado)"
if ($e.Estado -eq 'no conectada') {
  if (Test-TareaInstalada) {
    Write-Output '❌ El modo automático está instalado pero no hay ningún servidor corriendo ahora.'
    $d = Get-DiagnosticoRegistro
    if ($d) { Write-Output "   Registro: $d" }
    Write-Output ('   Registro completo: {0}' -f (Join-Path $CelularDir 'celular.log'))
  } else {
    Write-Output '❌ No hay ninguna conexión abierta: el celular no puede abrir sesiones nuevas en esta computadora.'
  }
} else {
  $e.Detalle | ForEach-Object { Write-Output $_ }
}
exit 0
