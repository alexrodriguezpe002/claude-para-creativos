# Conecta esta computadora con la app de Claude del celular (Remote Control) - Windows.
# Corre en una ventana de terminal y funciona mientras esté abierta. Si se corta, reconecta solo.
# Uso:  powershell -NoProfile -ExecutionPolicy Bypass -File conectar-celular.ps1 [-Carpeta RUTA]
# PENDIENTE DE PRUEBA en una PC con Windows.
param([string]$Carpeta = '')

. (Join-Path $PSScriptRoot 'comun.ps1')
$espera = if ($env:CELULAR_ESPERA) { [int]$env:CELULAR_ESPERA } else { 30 }
if (-not $Carpeta) { $Carpeta = $CarpetaPorDefecto }

Write-Host "`nConectar esta computadora con Claude en el celular`n"

# 0. Si ya hay una conexión abierta, no se abre otra (la segunda falla y parece que nada anda)
$ya = @(Get-Servidores)
if ($ya.Count -gt 0) {
  Write-Host ('✅ Ya está conectada (hace {0}). No hace falta nada más. Esta ventana ya se puede cerrar.' -f (Format-Duracion $ya[0].Segundos))
  exit 0
}

# 1. Claude Code con Remote Control
$bin = Find-Claude
if (-not $bin) {
  Write-Host '❌ No encontré Claude Code con Remote Control en esta computadora.'
  Write-Host '   Abre la app de Claude, entra una vez a la pestaña Code y vuelve a intentar.'
  exit 1
}
Clear-EnvClaude

# 2. Sesión iniciada (una sola vez)
$who = Get-Cuenta $bin
if (-not $who) {
  Write-Host 'Paso 1 · Iniciar sesión'
  Write-Host 'Se abre el navegador: entra con tu cuenta de Claude (la misma del celular) y toca «Authorize».'
  while (-not $who) {
    & $bin auth login --claudeai
    $who = Get-Cuenta $bin
    if (-not $who) { Read-Host 'No se completó. Aprieta Enter para intentar de nuevo' | Out-Null }
  }
}
Write-Host "✅ Sesión iniciada: $who`n"

# 3. La carpeta donde empiezan las sesiones del celular (nunca la de inicio: ahí pregunta «Trust» cada vez)
try {
  New-Item -ItemType Directory -Force -Path $Carpeta | Out-Null
  Set-Location -Path $Carpeta
} catch {
  Write-Host "❌ No pude abrir la carpeta $Carpeta."
  exit 1
}

# 4. Conectar
$spawn = @()
if ((& $bin remote-control --help 2>$null | Out-String) -match '--spawn') { $spawn = @('--spawn=same-dir') }
Write-Host 'Paso 2 · Conectar'
Write-Host 'Solo la primera vez puede preguntar dos cosas. A las dos: escribe y y aprieta Enter.'
Write-Host '  • «Enable Remote Control? (y/n)»   (¿activar el control desde el celular?)'
Write-Host "  • «Trust $Carpeta? [y/N]»   (¿confías en esta carpeta?)"
Write-Host 'Cuando diga «Connected», ya está. Deja esta ventana abierta y la computadora enchufada.'
Write-Host "Para desconectar: haz clic dentro de esta ventana y aprieta Ctrl + C, o ciérrala.`n"

$seguidas = 0
try {
  while ($true) {
    $inicio = Get-Date
    Set-NoDormir
    & $bin remote-control @spawn
    $codigo = $LASTEXITCODE
    Set-NoDormir -Quitar
    if ($codigo -eq 0) { break }

    if (@(Get-Servidores).Count -gt 0) {
      Write-Host "`n✅ Ya hay otra conexión abierta. Esta ventana ya se puede cerrar."
      exit 0
    }
    if (-not (Get-Cuenta $bin)) {
      Write-Host "`nSe cerró la sesión de Claude en la computadora. Se abre el navegador para entrar de nuevo..."
      & $bin auth login --claudeai
    }
    if (((Get-Date) - $inicio).TotalSeconds -lt 20) { $seguidas++ } else { $seguidas = 0 }
    if ($seguidas -ge 5) {
      Write-Host "`n❌ No logra conectar (5 intentos seguidos). El mensaje de arriba dice por qué."
      Write-Host '   Pídele a Claude «no conecta el celular» y pásale ese mensaje.'
      Read-Host 'Aprieta Enter para intentar de nuevo' | Out-Null
      $seguidas = 0
    } else {
      Write-Host "`nSe cortó la conexión (sin internet, la compu se durmió o se actualizó Claude)."
      Write-Host "   Vuelvo a conectar solo en $espera segundos. No tienes que hacer nada."
      Start-Sleep -Seconds $espera
    }
    $nuevo = Find-Claude
    if ($nuevo) { $bin = $nuevo }
  }
} finally {
  Set-NoDormir -Quitar
}
Write-Host "`nDesconectado. Ya puedes cerrar esta ventana."
