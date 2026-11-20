# comun.ps1 - lo que comparten los scripts de conectar-celular en Windows.
# Se carga con:  . (Join-Path $PSScriptRoot 'comun.ps1')
# PENDIENTE DE PRUEBA en una PC con Windows (escrito en una Mac, sin poder correrlo).
# Guardado en UTF-8 con BOM: sin BOM, Windows PowerShell 5.1 rompe las tildes.

try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$CelularDir = if ($env:CELULAR_DIR) { $env:CELULAR_DIR } else { Join-Path $env:USERPROFILE 'MI-SISTEMA-CLAUDE\celular' }
$NombreTarea = 'Claude - conectar celular'
$VersionMinima = [version]'2.1.139'      # la primera con Remote Control
$CarpetaPorDefecto = Join-Path $env:USERPROFILE 'PROYECTOS'   # nunca la carpeta de inicio (ver SKILL.md)
$ClaudeJson = if ($env:CLAUDE_JSON) { $env:CLAUDE_JSON } else { Join-Path $env:USERPROFILE '.claude.json' }
# «...\claude.exe remote-control» o «claude rc»; con npm: «node ...\cli.js remote-control»
$PatronServidor = '(?i)(claude(\.exe)?|cli\.js)"?\s+(remote-control|rc)(\s|$)'

function Get-VersionDe([string]$Ruta) {
  try { $o = (& $Ruta --version 2>$null | Out-String) } catch { return $null }
  if ($o -match '(\d+\.\d+\.\d+)\s*\(Claude Code\)') { return [version]$Matches[1] }
  return $null
}

# El primer Claude Code con Remote Control: el que trae la app de escritorio (el más nuevo),
# el del instalador oficial y el del PATH. Nunca el Claude.exe de la app (es otra cosa).
function Find-Claude {
  if ($env:CLAUDE_BIN) { return $env:CLAUDE_BIN }
  $cands = New-Object System.Collections.Generic.List[string]
  $base = Join-Path $env:APPDATA 'Claude\claude-code'
  if (Test-Path $base) {
    Get-ChildItem -Path $base -Recurse -Filter 'claude.exe' -ErrorAction SilentlyContinue |
      Sort-Object -Descending -Property @{ Expression = {
          $v = [version]'0.0.0'
          if ($_.FullName -match 'claude-code\\(\d+\.\d+\.\d+)') { $v = [version]$Matches[1] }
          $v } } |
      ForEach-Object { $cands.Add($_.FullName) }
  }
  $cands.Add((Join-Path $env:USERPROFILE '.local\bin\claude.exe'))
  $c = Get-Command claude -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c) { $cands.Add($c.Source) }
  foreach ($r in $cands) {
    if (-not (Test-Path $r)) { continue }
    $v = Get-VersionDe $r
    if ($v -and $v -ge $VersionMinima) { return $r }
  }
  return $null
}

# Cuenta con la que está iniciada la sesión del CLI, o $null
function Get-Cuenta([string]$Bin) {
  try { $o = (& $Bin auth status 2>$null | Out-String) } catch { return $null }
  if (-not $o) { return $null }
  try { $j = $o | ConvertFrom-Json } catch { return $null }
  if (-not $j.loggedIn) { return $null }
  foreach ($k in 'email', 'emailAddress', 'orgName', 'organizationName') { if ($j.$k) { return [string]$j.$k } }
  return 'tu cuenta'
}

# Quita las variables que le roban la conexión a Remote Control (si lo lanza otra sesión de Claude)
function Clear-EnvClaude {
  Get-ChildItem Env: | Where-Object {
      $_.Name -match '^(ANTHROPIC_|CLAUDECODE$|CLAUDE_CODE_|CLAUDE_AGENT_SDK_|DISABLE_GROWTHBOOK$)' -and
      $_.Name -ne 'CLAUDE_CODE_GIT_BASH_PATH' } |
    ForEach-Object { Remove-Item -Path ('Env:' + $_.Name) -ErrorAction SilentlyContinue }
}

# Servidores de Remote Control de este usuario: objetos con Pid, Padre y Segundos
function Get-Servidores {
  $patron = if ($env:CELULAR_PATRON) { $env:CELULAR_PATRON } else { $PatronServidor }
  $envoltorios = @('powershell.exe', 'pwsh.exe', 'cmd.exe', 'conhost.exe', 'wscript.exe')
  $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and ($_.CommandLine -match $patron) -and ($envoltorios -notcontains $_.Name.ToLower()) }
  foreach ($p in $procs) {
    try {
      $o = Invoke-CimMethod -InputObject $p -MethodName GetOwner -ErrorAction Stop
      if ($o.User -and ($o.User -ne $env:USERNAME)) { continue }
    } catch { }
    $seg = 0
    if ($p.CreationDate) { $seg = [int]((Get-Date) - $p.CreationDate).TotalSeconds }
    [pscustomobject]@{ Pid = [int]$p.ProcessId; Padre = [int]$p.ParentProcessId; Segundos = $seg }
  }
}

function Get-Conexiones([int]$ProcId) {
  try { return @(Get-NetTCPConnection -OwningProcess $ProcId -State Established -ErrorAction Stop).Count } catch { return 0 }
}

# ¿Ya se respondieron las dos preguntas de la primera vez en esa carpeta?
function Get-PrimeraVez([string]$Carpeta) {
  $r = [pscustomobject]@{ Dialogo = $false; Confianza = $false }
  try { $j = Get-Content -Raw -Encoding UTF8 -Path $ClaudeJson | ConvertFrom-Json } catch { return $r }
  $r.Dialogo = ($j.remoteDialogSeen -eq $true)
  if ($j.projects) {
    # La confianza se hereda de una carpeta madre (por ejemplo la de usuario): se sube hasta la raíz.
    $dir = $Carpeta.TrimEnd('\', '/')
    while ($dir -and -not $r.Confianza) {
      foreach ($k in @($dir, ($dir -replace '\\', '/'))) {
        $p = $j.projects.PSObject.Properties[$k]
        if ($p -and ($p.Value.hasTrustDialogAccepted -eq $true)) { $r.Confianza = $true }
      }
      $padre = Split-Path -Parent $dir
      if (-not $padre -or $padre -eq $dir) { break }
      $dir = $padre
    }
  }
  return $r
}

# Que la compu no se duerma mientras corre el servidor (solo mientras corre, no cambia ajustes)
function Set-NoDormir([switch]$Quitar) {
  try {
    if (-not ('CelularWin32.Energia' -as [type])) {
      Add-Type -Namespace CelularWin32 -Name Energia -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
    }
    if ($Quitar) { [void][CelularWin32.Energia]::SetThreadExecutionState([uint32]2147483648) }   # ES_CONTINUOUS
    else { [void][CelularWin32.Energia]::SetThreadExecutionState([uint32]2147483649) }           # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
  } catch { }
}

function Test-TareaInstalada {
  return ($null -ne (Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue))
}

function Format-Duracion([int]$s) {
  if ($s -lt 60) { return "$s s" }
  if ($s -lt 3600) { return ('{0} min' -f [math]::Floor($s / 60)) }
  if ($s -lt 86400) { return ('{0} h {1} min' -f [math]::Floor($s / 3600), [math]::Floor(($s % 3600) / 60)) }
  return ('{0} días' -f [math]::Floor($s / 86400))
}

# Traduce el final del registro del modo automático a una frase
function Get-DiagnosticoRegistro {
  $t = ''
  foreach ($f in 'celular.log', 'servidor.log', 'servidor-errores.log') {
    $ruta = Join-Path $CelularDir $f
    if (Test-Path $ruta) { $t += ((Get-Content -Path $ruta -Tail 60 -ErrorAction SilentlyContinue) -join "`n") + "`n" }
  }
  if ($t -match 'ESPERA ya hay otra') { return 'Espera: ya hay otra conexión abierta. Cuando se cierre, el automático la reemplaza solo.' }
  if ($t -match 'Workspace not trusted|FALTA primera vez') { return 'Falta responder una vez a mano las preguntas de la primera vez en esa carpeta (conectar con la ventana de terminal).' }
  if ($t -match 'got no answer') { return 'Falta responder «Enable Remote Control? (y/n)» una vez a mano.' }
  if ($t -match 'must be logged in|requires a claude.ai subscription|SIN SESION') { return 'Se cerró la sesión de Claude en la computadora: conectar una vez a mano (abre el navegador).' }
  if ($t -match "isn't enabled for this account") { return 'La cuenta no tiene Remote Control habilitado. Cerrar y abrir sesión lo refresca.' }
  if ($t -match "Couldn't verify Remote Control eligibility|ENOTFOUND|ECONNREFUSED") { return 'Sin internet o algo bloquea la conexión. Reintenta solo.' }
  if ($t -match 'SIN CLAUDE') { return 'No encuentra Claude Code: abrir la app de Claude y entrar una vez a la pestaña Code.' }
  if ($t -match 'Connected') { return 'El registro dice Connected.' }
  return ''
}
