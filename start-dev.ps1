# ============================================================
# AI Meeting Agent - Local Development Startup
# File: start-dev.ps1
# ============================================================

$ErrorActionPreference = "Continue"

$ProjectRoot = $PSScriptRoot
$MobileDir = Join-Path $ProjectRoot "apps\mobile"

. (Join-Path $ProjectRoot 'scripts\local-env.ps1')
Import-ProjectEnv -ProjectRoot $ProjectRoot

$WorkerPort = 8001
$ApiPort = 8002
$ExpoPort = 8081
$OllamaPort = 11434
$PostgresPort = 5432
Set-EnvDefault -Name 'DATABASE_URL' -Value 'postgresql+psycopg://meeting_agent:meeting_agent@127.0.0.1:5432/meeting_agent'
Set-EnvDefault -Name 'STORAGE_DIR' -Value (Join-Path $ProjectRoot 'storage')
Set-EnvDefault -Name 'WORKER_URL' -Value "http://127.0.0.1:$WorkerPort"
Set-EnvDefault -Name 'OLLAMA_MODEL' -Value 'qwen3:14b'
Set-EnvDefault -Name 'OLLAMA_BASE_URL' -Value "http://127.0.0.1:$OllamaPort"
$env:DATABASE_URL = Convert-LocalDatabaseUrl $env:DATABASE_URL
$OllamaModel = $env:OLLAMA_MODEL

Write-Host ""
Write-Host "============================================================"
Write-Host " AI Meeting Agent - Development Startup"
Write-Host "============================================================"
Write-Host ""

Set-Location $ProjectRoot


function Test-Port {
    param(
        [int]$Port
    )

    $connection = Get-NetTCPConnection `
        -LocalPort $Port `
        -State Listen `
        -ErrorAction SilentlyContinue

    return $null -ne $connection
}


function Wait-HttpHealth {
    param(
        [string]$Name,
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )

    Write-Host "Waiting for $Name..."

    for ($i = 0; $i -lt $TimeoutSeconds; $i++) {
        try {
            $response = Invoke-RestMethod `
                -Uri $Url `
                -Method Get `
                -TimeoutSec 2 `
                -ErrorAction Stop

            Write-Host "[OK] $Name is ready"
            return $true
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    Write-Host "[ERROR] $Name health check timeout"
    return $false
}


# ============================================================
# 1. PostgreSQL
# ============================================================

Write-Host ""
Write-Host "[1/6] Checking PostgreSQL..."

$pgResult = Test-NetConnection `
    127.0.0.1 `
    -Port $PostgresPort `
    -InformationLevel Quiet `
    -WarningAction SilentlyContinue

if ($pgResult) {
    Write-Host "[OK] PostgreSQL :$PostgresPort"
}
else {
    Write-Host ""
    Write-Host "[ERROR] PostgreSQL is not available on port $PostgresPort"
    Write-Host ""
    Write-Host "Please start PostgreSQL first."
    Write-Host "Startup cancelled."
    exit 1
}


# ============================================================
# 2. Ollama
# ============================================================

Write-Host ""
Write-Host "[2/6] Checking Ollama..."

$ollamaReady = $false

try {
    $tags = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$OllamaPort/api/tags" `
        -Method Get `
        -TimeoutSec 3 `
        -ErrorAction Stop

    $ollamaReady = $true
    Write-Host "[OK] Ollama :$OllamaPort"

    $modelFound = $false

    foreach ($model in $tags.models) {
        if ($model.name -eq $OllamaModel) {
            $modelFound = $true
            break
        }
    }

    if ($modelFound) {
        Write-Host "[OK] Model $OllamaModel found"
    }
    else {
        Write-Host "[WARNING] $OllamaModel was not found"
        Write-Host "Run: ollama pull $OllamaModel"
    }
}
catch {
    Write-Host "[WARNING] Ollama is not running"
    Write-Host "Starting Ollama..."

    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoExit",
            "-Command",
            "ollama serve"
        )

    Start-Sleep -Seconds 5

    try {
        Invoke-RestMethod `
            -Uri "http://127.0.0.1:$OllamaPort/api/tags" `
            -TimeoutSec 3 `
            -ErrorAction Stop | Out-Null

        Write-Host "[OK] Ollama started"
    }
    catch {
        Write-Host "[ERROR] Ollama startup failed"
        Write-Host "Please check Ollama installation."
        exit 1
    }
}


# ============================================================
# 3. Worker
# ============================================================

Write-Host ""
Write-Host "[3/6] Checking Worker..."

if (Test-Port $WorkerPort) {

    $workerPid = (
        Get-NetTCPConnection `
            -LocalPort $WorkerPort `
            -State Listen
    ).OwningProcess

    Write-Host "[OK] Worker already running"
    Write-Host "     Port: $WorkerPort"
    Write-Host "     PID : $workerPid"
}
else {

    Write-Host "Starting Worker..."

    $workerCommand = @"
Set-Location '$ProjectRoot'
Write-Host 'AI Meeting Worker'
Write-Host 'Watch for [ANALYST] and [OLLAMA] logs'
Write-Host ''
powershell -ExecutionPolicy Bypass -File '.\services\worker\start-worker-local.ps1'
"@

    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoExit",
            "-Command",
            $workerCommand
        )

    $workerReady = Wait-HttpHealth `
        -Name "Worker" `
        -Url "http://127.0.0.1:$WorkerPort/health" `
        -TimeoutSeconds 30

    if (-not $workerReady) {
        Write-Host "[ERROR] Worker failed to start"
        exit 1
    }
}


# ============================================================
# 4. API
# ============================================================

Write-Host ""
Write-Host "[4/6] Checking API..."

if (Test-Port $ApiPort) {

    $apiPid = (
        Get-NetTCPConnection `
            -LocalPort $ApiPort `
            -State Listen
    ).OwningProcess

    Write-Host "[OK] API already running"
    Write-Host "     Port: $ApiPort"
    Write-Host "     PID : $apiPid"
}
else {

    Write-Host "Starting API..."

    $apiCommand = @"
Set-Location '$ProjectRoot'
Write-Host 'AI Meeting API'
Write-Host ''
powershell -ExecutionPolicy Bypass -File '.\services\api\start-api-local.ps1'
"@

    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoExit",
            "-Command",
            $apiCommand
        )

    $apiReady = Wait-HttpHealth `
        -Name "API" `
        -Url "http://127.0.0.1:$ApiPort/health" `
        -TimeoutSeconds 30

    if (-not $apiReady) {
        Write-Host "[ERROR] API failed to start"
        exit 1
    }
}


# ============================================================
# 5. Show LAN IP and API information
# ============================================================

Write-Host ""
Write-Host "[5/6] Detecting LAN address..."

$lanIp = Get-NetIPAddress `
    -AddressFamily IPv4 `
    -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.InterfaceAlias -notmatch "Loopback|vEthernet|WSL|Docker"
    } |
    Select-Object -First 1 -ExpandProperty IPAddress

if ($lanIp) {

    Write-Host "[OK] LAN IP: $lanIp"
    Write-Host "     API: http://${lanIp}:$ApiPort"

    try {
        Invoke-RestMethod `
            -Uri "http://${lanIp}:$ApiPort/health" `
            -TimeoutSec 3 `
            -ErrorAction Stop | Out-Null

        Write-Host "[OK] LAN API reachable"
    }
    catch {
        Write-Host "[WARNING] LAN API health check failed"
        Write-Host "Check Windows Firewall if Expo Go cannot reach API."
    }
}
else {
    Write-Host "[WARNING] Could not detect LAN IP"
}


# ============================================================
# 6. Expo
# ============================================================

Write-Host ""
Write-Host "[6/6] Starting Expo..."

if (-not (Test-Path $MobileDir)) {
    Write-Host "[ERROR] Mobile directory not found:"
    Write-Host $MobileDir
    exit 1
}

Set-Location $MobileDir

Write-Host ""
Write-Host "Mobile project:"
Write-Host $MobileDir
Write-Host ""

if (Test-Port $ExpoPort) {

    $expoPid = (
        Get-NetTCPConnection `
            -LocalPort $ExpoPort `
            -State Listen
    ).OwningProcess

    Write-Host "[OK] Expo already running"
    Write-Host "     Port: $ExpoPort"
    Write-Host "     PID : $expoPid"
    Write-Host ""
    Write-Host "All services are ready."
}
else {

    Write-Host "============================================================"
    Write-Host " SERVICES READY"
    Write-Host "============================================================"
    Write-Host ""
    Write-Host "PostgreSQL : 127.0.0.1:$PostgresPort"
    Write-Host "Ollama     : 127.0.0.1:$OllamaPort"
    Write-Host "Worker     : 127.0.0.1:$WorkerPort"
    Write-Host "API        : 127.0.0.1:$ApiPort"

    if ($lanIp) {
        Write-Host "Mobile API : http://${lanIp}:$ApiPort"
    }

    Write-Host ""
    Write-Host "Starting Expo..."
    Write-Host ""

    npx expo start --clear --host lan --port $ExpoPort
}
