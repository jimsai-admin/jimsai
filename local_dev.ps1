$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendApp = Join-Path $Root "prototype\app.py"
$FrontendDir = Join-Path $Root "frontend"
$VenvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$NpmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
$LogDir = Join-Path $Root ".logs"
$BackendOutLog = Join-Path $LogDir "local-backend.out.log"
$BackendErrLog = Join-Path $LogDir "local-backend.err.log"
$FrontendOutLog = Join-Path $LogDir "local-frontend.out.log"
$FrontendErrLog = Join-Path $LogDir "local-frontend.err.log"

if (-not (Test-Path $BackendApp)) {
    throw "Backend app not found: $BackendApp"
}

if (-not (Test-Path $FrontendDir)) {
    throw "Frontend folder not found: $FrontendDir"
}

if (-not $NpmCmd) {
    throw "npm.cmd was not found on PATH"
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Set-Content -Path $BackendOutLog -Value ""
Set-Content -Path $BackendErrLog -Value ""
Set-Content -Path $FrontendOutLog -Value ""
Set-Content -Path $FrontendErrLog -Value ""

$python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

function Test-PortAvailable {
    param(
        [int]$Port
    )

    $listener = $null
    try {
        $address = [System.Net.IPAddress]::Parse("127.0.0.1")
        $listener = [System.Net.Sockets.TcpListener]::new($address, $Port)
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

function Get-AvailablePort {
    param(
        [int]$StartPort,
        [int]$EndPort
    )

    for ($port = $StartPort; $port -le $EndPort; $port++) {
        if (Test-PortAvailable -Port $port) {
            return $port
        }
    }

    throw "No available port found from $StartPort to $EndPort"
}

$BackendPort = Get-AvailablePort -StartPort 8000 -EndPort 8010
$FrontendPort = Get-AvailablePort -StartPort 3001 -EndPort 3010
$BackendUrl = "http://127.0.0.1:$BackendPort"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"
$FrontendOriginLocalhost = "http://localhost:$FrontendPort"
$FrontendOriginLoopback = "http://127.0.0.1:$FrontendPort"
$FrontendEnvLocal = Join-Path $FrontendDir ".env.local"

if ($BackendPort -ne 8000) {
    Write-Host "Port 8000 is busy; using backend port $BackendPort."
}

if ($FrontendPort -ne 3001) {
    Write-Host "Port 3001 is busy; using frontend port $FrontendPort."
}

$existingCorsOrigins = $env:CORS_ORIGINS
if ([string]::IsNullOrWhiteSpace($existingCorsOrigins)) {
    $env:CORS_ORIGINS = "$FrontendOriginLocalhost,$FrontendOriginLoopback,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3000,http://127.0.0.1:3000"
}
elseif ($existingCorsOrigins -notlike "*$FrontendOriginLocalhost*") {
    $env:CORS_ORIGINS = "$existingCorsOrigins,$FrontendOriginLocalhost,$FrontendOriginLoopback"
}

$env:NEXT_PUBLIC_API_BASE_URL = $BackendUrl

$frontendEnvLines = @(
    "NEXT_PUBLIC_API_BASE_URL=$BackendUrl"
)
Set-Content -Path $FrontendEnvLocal -Value $frontendEnvLines

Write-Host "Starting backend:  $BackendUrl"
Write-Host "Frontend API:     $BackendUrl"
$backend = Start-Process -FilePath $python `
    -ArgumentList "-m", "uvicorn", "prototype.app:app", "--reload", "--host", "127.0.0.1", "--port", "$BackendPort" `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $BackendOutLog `
    -RedirectStandardError $BackendErrLog `
    -NoNewWindow `
    -PassThru

Write-Host "Starting frontend: $FrontendUrl"
$frontend = Start-Process -FilePath $NpmCmd `
    -ArgumentList "run", "dev", "--", "-H", "127.0.0.1", "-p", "$FrontendPort" `
    -WorkingDirectory $FrontendDir `
    -RedirectStandardOutput $FrontendOutLog `
    -RedirectStandardError $FrontendErrLog `
    -NoNewWindow `
    -PassThru

Write-Host ""
Write-Host "Dev servers running in this terminal. Press Ctrl+C to stop."

$positions = @{
    $BackendOutLog = 0
    $BackendErrLog = 0
    $FrontendOutLog = 0
    $FrontendErrLog = 0
}

function Show-NewLogContent {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path $Path)) {
        return
    }

    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        $stream.Seek($positions[$Path], [System.IO.SeekOrigin]::Begin) | Out-Null
        $reader = New-Object System.IO.StreamReader($stream)
        $text = $reader.ReadToEnd()
        $positions[$Path] = $stream.Position

        if ($text.Length -gt 0) {
            foreach ($line in ($text -split "`r?`n")) {
                if ($line.Length -gt 0) {
                    Write-Host "[$Label] $line"
                }
            }
        }
    }
    finally {
        $stream.Dispose()
    }
}

try {
    while ($true) {
        Show-NewLogContent -Path $BackendOutLog -Label "backend"
        Show-NewLogContent -Path $BackendErrLog -Label "backend"
        Show-NewLogContent -Path $FrontendOutLog -Label "frontend"
        Show-NewLogContent -Path $FrontendErrLog -Label "frontend"

        $backend.Refresh()
        $frontend.Refresh()

        if ($backend.HasExited -or $frontend.HasExited) {
            Show-NewLogContent -Path $BackendOutLog -Label "backend"
            Show-NewLogContent -Path $BackendErrLog -Label "backend"
            Show-NewLogContent -Path $FrontendOutLog -Label "frontend"
            Show-NewLogContent -Path $FrontendErrLog -Label "frontend"
            throw "One of the dev servers stopped. Backend exited: $($backend.HasExited), Frontend exited: $($frontend.HasExited)"
        }

        Start-Sleep -Seconds 1
    }
}
finally {
    foreach ($process in @($backend, $frontend)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
