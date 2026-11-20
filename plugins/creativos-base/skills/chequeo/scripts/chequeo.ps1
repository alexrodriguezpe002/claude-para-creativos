# chequeo.ps1 — revisa si esta PC con Windows tiene todo lo que usa el kit. SOLO MIRA: no instala,
# no cambia ni borra nada. Misma salida que chequeo.sh (Mac y Linux).
#   powershell -ExecutionPolicy Bypass -File chequeo.ps1
# Funciona en Windows PowerShell 5.1 y en PowerShell 7. Guardado en UTF-8 con BOM (PowerShell 5.1
# lo necesita para leer bien los tildes y los emojis).

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$ErrorActionPreference = "SilentlyContinue"

$C = Join-Path $HOME ".claude"
$Aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginRoot = (Resolve-Path (Join-Path $Aqui "..\..\..")).Path

$script:Ok = 0; $script:Mal = 0; $script:Aviso = 0; $script:Codigos = @()
function Ok($que, $detalle) { $script:Ok++; Write-Output ("✅ {0} — {1}" -f $que, $detalle) }
function Mal($que, $detalle, $codigo) {
  $script:Mal++; $script:Codigos += $codigo
  Write-Output ("❌ {0} — {1} · arreglo: [{2}]" -f $que, $detalle, $codigo)
}
function Aviso($que, $detalle, $codigo) {
  $script:Aviso++
  if ($codigo) { $script:Codigos += $codigo; Write-Output ("⚠️  {0} — {1} · [{2}]" -f $que, $detalle, $codigo) }
  else { Write-Output ("⚠️  {0} — {1}" -f $que, $detalle) }
}
function Buscar($nombre, $extras) {
  $c = Get-Command $nombre -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c -and $c.Source -notlike "*\WindowsApps\*") { return $c.Source }
  foreach ($e in $extras) { if ($e -and (Test-Path $e)) { return $e } }
  return $null
}
# ¿El programa arranca de verdad? Uno instalado puede estar roto (le falta una librería).
function Anda($exe, $flag) {
  try { $null = (& $exe $flag 2>$null); return ($LASTEXITCODE -eq 0) } catch { return $false }
}
function LeerJson($ruta) {
  if (-not (Test-Path $ruta)) { return $null }
  try { return (Get-Content -Raw -Encoding UTF8 $ruta | ConvertFrom-Json) } catch { return $null }
}

# prefijo de los plugins del kit: el nombre de este plugin sin "-base"
$Prefijo = "creativos-"
$pj = LeerJson (Join-Path $PluginRoot ".claude-plugin\plugin.json")
if ($pj -and $pj.name -like "*-base") { $Prefijo = $pj.name.Substring(0, $pj.name.Length - 4) }

$dias = @("dom", "lun", "mar", "mié", "jue", "vie", "sáb")
$ahora = Get-Date
Write-Output ("Chequeo del kit · {0} {1}" -f $dias[[int]$ahora.DayOfWeek], $ahora.ToString("dd-MM-yyyy HH:mm"))
Write-Output "(solo mira: no instala ni cambia nada)"
Write-Output ""

# ------------------------------------------------------------------ 1. sistema
$os = [System.Environment]::OSVersion.Version
$arch = $env:PROCESSOR_ARCHITECTURE
if ($os.Major -ge 10) { Ok "sistema" ("Windows {0}.{1} (compilación {2}) · {3}" -f $os.Major, $os.Minor, $os.Build, $arch) }
else { Aviso "sistema" ("Windows {0}.{1} es viejo: el kit pide Windows 10 u 11" -f $os.Major, $os.Minor) "" }

# ------------------------------------------------------------------ 2. git y Git Bash
$pf = $env:ProgramFiles
$git = Buscar "git" @("$pf\Git\cmd\git.exe")
if ($git -and (Anda $git "--version")) { Ok "git" ((& $git --version) | Select-Object -First 1) }
elseif ($git) { Mal "git" "$git está pero no arranca (instalación rota)" "git-win" }
else { Mal "git" "no está (se instala con Git for Windows)" "git-win" }
$sh = Buscar "sh" @("$pf\Git\bin\sh.exe", "$pf\Git\usr\bin\sh.exe")
if ($sh) { Ok "Git Bash" "está (lo usan los hooks del registro de proyectos)" }
else { Mal "Git Bash" "no está: sin él no corren los hooks del registro (viene con Git for Windows)" "git-win" }

# ------------------------------------------------------------------ 3. gh (GitHub)
$gh = Buscar "gh" @("$pf\GitHub CLI\gh.exe", "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe")
if (-not $gh) { Mal "gh (GitHub)" "no está (hace falta para proponer y revisar mejoras del kit)" "gh-instalar" }
elseif (-not (Anda $gh "--version")) { Mal "gh (GitHub)" "$gh está pero no arranca (instalación rota)" "gh-instalar" }
else {
  Ok "gh (GitHub)" ((& $gh --version) | Select-Object -First 1)
  $estado = (& $gh auth status 2>&1) | Out-String
  if ($LASTEXITCODE -eq 0) {
    $cuenta = ""
    if ($estado -match "account ([A-Za-z0-9-]+)") { $cuenta = $Matches[1] }
    elseif ($estado -match "as ([A-Za-z0-9-]+)") { $cuenta = $Matches[1] }
    if ($cuenta) { Ok "GitHub: sesión" "conectado como $cuenta" } else { Ok "GitHub: sesión" "conectado" }
  } else { Mal "GitHub: sesión" "gh no tiene una cuenta conectada" "gh-login" }
}

# ------------------------------------------------------------------ 4. Python
$py = $null; $pyver = $null
foreach ($cand in @("py -3", "python3", "python")) {
  $partes = $cand -split " "
  $exe = Buscar $partes[0] @()
  if (-not $exe) { continue }
  $args2 = @($partes | Select-Object -Skip 1)
  $v = (& $exe @args2 -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null) | Select-Object -First 1
  if ($LASTEXITCODE -eq 0 -and $v) { $py = $cand; $pyver = $v; break }
}
if ($py) {
  if ($pyver -match "^3\.([0-6])\." -or $pyver -match "^2\.") { Mal "Python" "$pyver es muy viejo (hace falta 3.7 o más nuevo)" "python-instalar" }
  else { Ok "Python" "$pyver ($py)" }
} else { Mal "Python" "no está (sin Python no funcionan el registro de proyectos ni varios scripts)" "python-instalar" }

# ------------------------------------------------------------------ 5. plugins del kit
$instalados = @()
$inst = LeerJson (Join-Path $C "plugins\installed_plugins.json")
if ($inst -and $inst.plugins) {
  $instalados = @($inst.plugins.PSObject.Properties.Name | Where-Object { $_ -like "$Prefijo*" })
}
$sincronizados = @()
$syncDir = Join-Path $C "plugins\synced"
if (Test-Path $syncDir) {
  Get-ChildItem -Path $syncDir -Recurse -Depth 4 -Filter "plugin.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.Directory.Name -eq ".claude-plugin" } | ForEach-Object {
      $j = LeerJson $_.FullName
      if ($j -and $j.name -like "$Prefijo*") { $sincronizados += $j.name }
    }
}
# Los apagados en settings.json ("enabledPlugins": {"creativos-video@creativos": false}) no cuentan.
$apagados = @()
$setP = LeerJson (Join-Path $C "settings.json")
if ($setP -and $setP.enabledPlugins) {
  foreach ($pp in $setP.enabledPlugins.PSObject.Properties) {
    if ($pp.Value -eq $false) { $apagados += ($pp.Name -replace "@.*$", "") }
  }
}
function Tiene($n) {
  if ($apagados -contains $n) { return $false }
  foreach ($x in $instalados) { if ($x -like "$n@*") { return $true } }
  return ($sincronizados -contains $n)
}
if (Tiene "${Prefijo}base") {
  $txt = ($instalados | ForEach-Object { $_ -replace "@.*$", "" }) -join " "
  if ($sincronizados.Count -gt 0) { $txt += " · desde la app: " + ($sincronizados -join " ") }
  Ok "plugins del kit" $txt.Trim()
} else { Mal "plugins del kit" "no está instalado ${Prefijo}base" "plugins-instalar" }
# La app instala todos los plugins de la tienda: cada uno suma skills a cada sesión
if ((Tiene "${Prefijo}video") -and (Tiene "${Prefijo}animacion") -and (Tiene "${Prefijo}oficina")) {
  Aviso "plugins de más" "están los 4 grupos: cada uno suma skills a cada sesión; deja solo los de tu trabajo" "plugins-elegir"
}
$video = (Tiene "${Prefijo}video") -or (Tiene "${Prefijo}animacion")

$lista = Join-Path $Aqui "..\references\skills-v1.txt"
$viejas = 0
if (Test-Path $lista) {
  Get-Content -Encoding UTF8 $lista | Where-Object { $_.Trim() -and -not $_.StartsWith("#") } | ForEach-Object {
    $nombre = ($_.Trim() -split "\s+")[0]
    if (Test-Path (Join-Path $C "skills\$nombre")) { $viejas++ }
  }
}
$setRuta = Join-Path $C "settings.json"
$setTexto = ""; if (Test-Path $setRuta) { $setTexto = Get-Content -Raw -Encoding UTF8 $setRuta }
$hooksv1 = $setTexto -match "skills[\\/]+mdfilesummary[\\/]+scripts[\\/]+md_files\.py"
if ($viejas -gt 0 -or $hooksv1) {
  $extra = ""; if ($hooksv1) { $extra = " y sus hooks en settings.json" }
  Aviso "instalación vieja (v1)" "$viejas skills del kit en ~/.claude/skills$extra" "v1-migrar"
}

# ------------------------------------------------------------------ 6. ffmpeg y node
if ($video) {
  $ff = Buscar "ffmpeg" @("$env:LOCALAPPDATA\Microsoft\WinGet\Links\ffmpeg.exe", "$pf\ffmpeg\bin\ffmpeg.exe", "C:\ffmpeg\bin\ffmpeg.exe")
  if ($ff -and (Anda $ff "-version")) {
    $primera = (& $ff -version) | Select-Object -First 1
    Ok "ffmpeg" ((($primera -split " ") | Select-Object -First 3) -join " ")
  }
  elseif ($ff) { Mal "ffmpeg" "$ff está pero no arranca (instalación rota)" "ffmpeg-instalar" }
  else { Mal "ffmpeg" "no está (lo usan las skills de video y de animación)" "ffmpeg-instalar" }
  $node = Buscar "node" @("$pf\nodejs\node.exe")
  $npx = Buscar "npx" @("$pf\nodejs\npx.cmd")
  if ($node -and $npx -and (Anda $node "--version") -and (Anda $npx "--version")) { Ok "node y npx" ("node " + (& $node --version) + " ($node)") }
  elseif ($node -and -not (Anda $node "--version")) { Mal "node y npx" "$node está pero no arranca (instalación rota)" "node-instalar" }
  elseif ($node) { Mal "node y npx" "hay node ($node) pero npx no anda" "node-instalar" }
  else { Mal "node y npx" "no está (lo usa HyperFrames y los controles de calidad)" "node-instalar" }
}

# ------------------------------------------------------------------ 7. memoria única
$set = LeerJson $setRuta
$mem = $null; if ($set) { $mem = $set.autoMemoryDirectory }
if ($mem) { Ok "memoria" "una sola, en $mem" }
else {
  $esc = ($HOME -replace "[^A-Za-z0-9]", "-")
  $vieja = Join-Path $C "projects\$esc\memory\MEMORY.md"
  if (Test-Path $vieja) { Mal "memoria" ("cada carpeta tiene su memoria (sugerida: la que ya existe, " + (Split-Path $vieja) + ")") "memoria-unica" }
  else { Mal "memoria" ("cada carpeta tiene su memoria (sugerida: " + (Join-Path $HOME "MI-SISTEMA-CLAUDE\memoria") + ")") "memoria-unica" }
}

# ------------------------------------------------------------------ 7b. carpeta de proyectos
$cjj = LeerJson (Join-Path $C "registro-proyectos\carpetas.json")
if ($cjj -and $cjj.raices) { Ok "carpeta de proyectos" "la que dice .claude\registro-proyectos\carpetas.json" }
elseif (Test-Path (Join-Path $HOME "PROYECTOS")) { Ok "carpeta de proyectos" (Join-Path $HOME "PROYECTOS") }
else { Mal "carpeta de proyectos" "no hay PROYECTOS en tu carpeta de usuario ni otra declarada (sin ella, Claude inventa dónde guardar cada trabajo)" "proyectos-carpeta" }

# ------------------------------------------------------------------ 8. perfil
$cmd = Join-Path $C "CLAUDE.md"
$perfil = Join-Path $HOME "MI-SISTEMA-CLAUDE\perfil.md"
if ((Test-Path $cmd) -and ((Get-Content -Raw -Encoding UTF8 $cmd) -match "MI-SISTEMA-CLAUDE/perfil\.md")) {
  $lineas = 0; if (Test-Path $perfil) { $lineas = @(Get-Content -Encoding UTF8 $perfil | Where-Object { $_.Trim() }).Count }
  if ($lineas -gt 5) { Ok "perfil" "~/.claude/CLAUDE.md lee ~/MI-SISTEMA-CLAUDE/perfil.md" }
  else { Mal "perfil" "el CLAUDE.md lo busca, pero el perfil está vacío o no existe" "perfil-conoceme" }
} elseif (Test-Path $cmd) { Mal "perfil" "~/.claude/CLAUDE.md existe pero no lee el perfil" "perfil-conoceme" }
elseif (Test-Path (Join-Path $HOME "CLAUDE.md")) { Mal "perfil" "no hay ~/.claude/CLAUDE.md (hay uno en ~/CLAUDE.md: solo lo leen las sesiones abiertas dentro de tu carpeta de usuario)" "perfil-conoceme" }
else { Mal "perfil" "no hay ~/.claude/CLAUDE.md ni perfil" "perfil-conoceme" }

# ------------------------------------------------------------------ 9. avisos al celular
if ($set -and $set.inputNeededNotifEnabled -eq $true -and $set.agentPushNotifEnabled -eq $true) { Ok "avisos al celular" "activados" }
else { Aviso "avisos al celular" "apagados (opcional: avisan cuando Claude necesita algo o termina)" "avisos-celular" }

Write-Output ""
Write-Output ("Resumen: {0} ✅ · {1} ❌ · {2} ⚠️" -f $script:Ok, $script:Mal, $script:Aviso)
if ($script:Codigos.Count -gt 0) { Write-Output ("CODIGOS: " + ($script:Codigos -join " ")) } else { Write-Output "CODIGOS: ninguno" }
exit 0
