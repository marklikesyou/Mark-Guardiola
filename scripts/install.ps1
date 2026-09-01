param([switch]$DryRun)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$markRepo = 'https://github.com/marklikesyou/Mark-Guardiola.git'
$markTarget = if ($env:MARK_INSTALL_DIR) { $env:MARK_INSTALL_DIR } else { Join-Path $env:USERPROFILE 'MarkGuardiola' }
$markArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Use scripts/install.sh on macOS or Linux.'
}
if ($markArchitecture -notin @('X64', 'Arm64')) { throw "Unsupported Windows architecture: $markArchitecture" }
if ($DryRun -or $env:MARK_INSTALL_DRY_RUN -eq '1') {
    Write-Output "Platform: Windows/$markArchitecture`nRepository: $markRepo`nDirectory: $markTarget"
    Write-Output 'Plan: verify Git/Docker/Compose; clone or reuse; create private .env; build; migrate; restore trusted bundle or rebuild real sources; check data/models; start production services.'
    return
}

function Invoke-MarkNative {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE). Existing user data has not been reset." }
}
foreach ($markCommand in @('git', 'docker')) {
    if (-not (Get-Command $markCommand -ErrorAction SilentlyContinue)) {
        throw "Missing prerequisite: $markCommand. Install Git for Windows and Docker Desktop with Linux containers, start Docker, then rerun."
    }
}
Invoke-MarkNative docker @('compose', 'version')
$markContainerOS = & docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $markContainerOS -ne 'linux') {
    throw 'Start Docker Desktop and switch to Linux containers, then rerun.'
}

if (Test-Path -LiteralPath $markTarget) {
    if (-not (Test-Path -LiteralPath (Join-Path $markTarget '.git') -PathType Container)) {
        throw "Refusing to change existing non-repository directory: $markTarget"
    }
    $markRemote = & git -C $markTarget remote get-url origin
    if ($LASTEXITCODE -ne 0 -or $markRemote -notin @($markRepo, 'https://github.com/marklikesyou/Mark-Guardiola', 'git@github.com:marklikesyou/Mark-Guardiola.git')) {
        throw 'Existing checkout has a different origin; select a new MARK_INSTALL_DIR.'
    }
    $markChanges = & git -C $markTarget status --porcelain
    if ($LASTEXITCODE -ne 0 -or $markChanges) { throw 'Existing checkout contains local changes. Preserve or commit them before installation.' }
    Write-Output 'Reusing existing checkout without pulling or changing its branch.'
} else {
    try { Invoke-MarkNative git @('clone', '--depth', '1', $markRepo, $markTarget) }
    catch { throw 'Repository clone failed. For a private repository, configure authenticated Git access and rerun. An empty/unpublished repository cannot be installed yet.' }
}
$markTarget = (Resolve-Path -LiteralPath $markTarget).Path
$markComposeFile = Join-Path $markTarget 'infra/compose.production.yml'
$markEnvFile = Join-Path $markTarget '.env'
if (-not (Test-Path -LiteralPath $markComposeFile)) {
    throw 'The checkout does not contain a complete installable release.'
}
if (-not (Test-Path -LiteralPath $markEnvFile)) {
    $markBytes = New-Object byte[] 24
    $markRandom = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $markRandom.GetBytes($markBytes) } finally { $markRandom.Dispose() }
    $markPassword = [BitConverter]::ToString($markBytes).Replace('-', '').ToLowerInvariant()
    $markLines = @(
        'MARK_HTTP_PORT=3000'
        "POSTGRES_PASSWORD=$markPassword"
        'MARK_API_FOOTBALL_KEY='
        'MARK_FOOTBALL_DATA_ORG_KEY='
        'MARK_API_FOOTBALL_DAILY_LIMIT=100'
        'MARK_DEFAULT_SIMULATIONS=10000'
        'MARK_LOG_LEVEL=INFO'
        'MARK_BOOTSTRAP_MODE=auto'
        ''
        'MARK_BUNDLE_FILE='
        'MARK_BUNDLE_SHA256='
    )
    $markContent = [string]::Join([Environment]::NewLine, $markLines) + [Environment]::NewLine
    $markFile = [IO.File]::Open($markEnvFile, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $markWriter = New-Object IO.StreamWriter($markFile, (New-Object Text.UTF8Encoding($false)))
        try { $markWriter.Write($markContent) } finally { $markWriter.Dispose() }
    } finally { $markFile.Dispose() }
    $markAcl = New-Object Security.AccessControl.FileSecurity
    $markAcl.SetAccessRuleProtection($true, $false)
    $markIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $markRule = New-Object Security.AccessControl.FileSystemAccessRule($markIdentity, 'FullControl', 'Allow')
    $markAcl.AddAccessRule($markRule)
    Set-Acl -LiteralPath $markEnvFile -AclObject $markAcl
    Remove-Variable markPassword, markContent, markBytes, markLines
}
$markConfig = [IO.File]::ReadAllText($markEnvFile)
if ($markConfig -notmatch '(?m)^POSTGRES_PASSWORD=[A-Za-z0-9_-]{24,}\r?$') {
    throw 'POSTGRES_PASSWORD in .env must contain at least 24 URL-safe characters. Existing configuration was preserved.'
}
if ($env:POSTGRES_PASSWORD -and $env:POSTGRES_PASSWORD -notmatch '^[A-Za-z0-9_-]{24,}$') {
    throw 'The POSTGRES_PASSWORD environment override is not URL-safe or is too short.'
}
[IO.Directory]::CreateDirectory((Join-Path $markTarget 'bundles')) | Out-Null
$markCompose = @('compose', '--env-file', $markEnvFile, '-f', $markComposeFile)
Write-Output 'Building the full application. A first real-source rebuild can take hours and several GB; no sample data is substituted.'
Write-Output 'Optional provider keys: set MARK_API_FOOTBALL_KEY / MARK_FOOTBALL_DATA_ORG_KEY in .env. Trusted bundle: set MARK_BUNDLE_FILE=/bundles/filename.zip and MARK_BUNDLE_SHA256, and place it in bundles/.'
Invoke-MarkNative docker ($markCompose + @('build', 'api', 'frontend'))
Invoke-MarkNative docker ($markCompose + @('up', '-d', '--wait', '--wait-timeout', '120', 'db', 'redis'))
Invoke-MarkNative docker ($markCompose + @('run', '--rm', 'migrate'))
Invoke-MarkNative docker ($markCompose + @('run', '--rm', '--no-deps', 'bootstrap'))
Invoke-MarkNative docker ($markCompose + @('up', '-d', '--wait', '--wait-timeout', '180', 'api', 'worker', 'frontend'))
Invoke-MarkNative docker ($markCompose + @('exec', '-T', 'api', 'markguardiola', 'install-status'))
$markPort = if ($env:MARK_HTTP_PORT) { $env:MARK_HTTP_PORT } elseif ($markConfig -match '(?m)^MARK_HTTP_PORT=(\d+)\r?$') { $Matches[1] } else { '3000' }
Invoke-RestMethod -Uri "http://127.0.0.1:$markPort/ready" -TimeoutSec 15 | Out-Null
Write-Output "MarkGuardiola is ready: http://localhost:$markPort`nInstallation: $markTarget"
