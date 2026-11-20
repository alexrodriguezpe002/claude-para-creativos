# Arranque del modo «siempre conectado» en Windows. Lo lanza el Programador de tareas al iniciar
# sesión (o el acceso de la carpeta Inicio) y se queda corriendo: si el servidor se cae, lo vuelve
# a arrancar. Vive copiado en %USERPROFILE%\MI-SISTEMA-CLAUDE\celular\ (ruta fija).
# PENDIENTE DE PRUEBA en una PC con Windows.

. (Join-Path $PSScriptRoot 'comun.ps1')
New-Item -ItemType Directory -Force -Path $CelularDir | Out-Null
$Log = Join-Path $CelularDir 'celular.log'
function Write-Registro([string]$m) {
  Add-Content -Path $Log -Value ('{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) -Encoding UTF8
}
if ((Test-Path $Log) -and ((Get-Item $Log).Length -gt 1MB)) { Move-Item -Force $Log "$Log.1" }

$carpeta = ''
$txt = Join-Path $CelularDir 'carpeta.txt'
if (Test-Path $txt) { $carpeta = (Get-Content -Path $txt -Encoding UTF8 | Select-Object -First 1) }
if (-not $carpeta) { $carpeta = $CarpetaPorDefecto }
Clear-EnvClaude

while ($true) {
  $bin = Find-Claude
  if (-not $bin) { Write-Registro 'SIN CLAUDE: no encuentro Claude Code con Remote Control'; Start-Sleep -Seconds 300; continue }
  if (-not (Get-Cuenta $bin)) { Write-Registro 'SIN SESION: falta iniciar sesión (conectar una vez a mano)'; Start-Sleep -Seconds 300; continue }
  $pv = Get-PrimeraVez $carpeta
  if (-not ($pv.Dialogo -and $pv.Confianza)) {
    Write-Registro ("FALTA primera vez en {0} (dialogo={1} confianza={2})" -f $carpeta, $pv.Dialogo, $pv.Confianza)
    Start-Sleep -Seconds 600; continue
  }
  if (@(Get-Servidores).Count -gt 0) { Write-Registro 'ESPERA ya hay otra conexión abierta'; Start-Sleep -Seconds 60; continue }
  if (-not (Test-Path $carpeta)) { New-Item -ItemType Directory -Force -Path $carpeta | Out-Null }

  $spawn = @()
  if ((& $bin remote-control --help 2>$null | Out-String) -match '--spawn') { $spawn = @('--spawn=same-dir') }
  Write-Registro ("ARRANCA {0} en {1}" -f $bin, $carpeta)
  Set-NoDormir
  try {
    $p = Start-Process -FilePath $bin -ArgumentList (@('remote-control') + $spawn + @('--verbose')) `
      -WorkingDirectory $carpeta -NoNewWindow -PassThru -Wait `
      -RedirectStandardOutput (Join-Path $CelularDir 'servidor.log') `
      -RedirectStandardError (Join-Path $CelularDir 'servidor-errores.log')
    Write-Registro ("TERMINO con código {0}" -f $p.ExitCode)
  } catch {
    Write-Registro ("ERROR al arrancar: {0}" -f $_.Exception.Message)
  }
  Set-NoDormir -Quitar
  Start-Sleep -Seconds 30
}
