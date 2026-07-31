param(
    [string]$HostIp,
    [ValidateSet('tunnel', 'lan')]
    [string]$ExpoHostMode = 'lan',
    [switch]$RestartExpo
)

$ErrorActionPreference = 'Stop'
if (-not $ExpoHostMode) {
    $ExpoHostMode = 'tunnel'
}
$ExpoHostMode = $ExpoHostMode.Trim().ToLowerInvariant()
Write-Host "Expo host mode: $ExpoHostMode"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$MobileDir = Join-Path $ProjectRoot 'apps\mobile'
$ApiDir = Join-Path $ProjectRoot 'services\api'
$WorkerDir = Join-Path $ProjectRoot 'services\worker'

. (Join-Path $ProjectRoot 'scripts\local-env.ps1')

function Get-LocalHostIp {
    $configs = Get-NetIPConfiguration |
        Where-Object {
            $_.IPv4Address -and
            $_.NetAdapter.Status -eq 'Up' -and
            $_.InterfaceAlias -notmatch 'vEthernet|Docker|Loopback|VMware|VirtualBox'
        } |
        Sort-Object @{ Expression = { if ($_.IPv4DefaultGateway) { 0 } else { 1 } } },
                    @{ Expression = { if ($_.InterfaceAlias -eq 'WLAN' -or $_.InterfaceAlias -eq 'Wi-Fi') { 0 } else { 1 } } },
                    @{ Expression = { if ($_.InterfaceAlias -match 'WLAN|Wi-Fi|以太网|Ethernet') { 0 } else { 1 } } }

    foreach ($config in $configs) {
        foreach ($address in $config.IPv4Address) {
            if ($address.IPAddress -and $address.IPAddress -notlike '127.*' -and $address.IPAddress -notlike '169.254.*') {
                return $address.IPAddress
            }
        }
    }

    throw 'No usable LAN IPv4 address found. Pass -HostIp manually, for example: .\scripts\start-local-app.ps1 -HostIp 192.168.1.6'
}

function Set-MobileEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $envPath = Join-Path $MobileDir '.env'
    $lines = if (Test-Path $envPath) { @(Get-Content $envPath -Encoding UTF8) } else { @() }
    $nextLines = New-Object System.Collections.Generic.List[string]
    $found = $false

    foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($Name))\s*=") {
            $nextLines.Add("$Name=$Value")
            $found = $true
        } else {
            $nextLines.Add($line)
        }
    }

    if (-not $found) {
        $nextLines.Add("$Name=$Value")
    }

    Set-Content -Path $envPath -Value $nextLines -Encoding UTF8
}

function Enable-LocalFirewallPorts {
    $ruleName = 'AI Meeting Agent Local Dev Ports'
    $ports = @('8081', '8002', '8001')

    try {
        Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
            Remove-NetFirewallRule -ErrorAction SilentlyContinue
        New-NetFirewallRule -DisplayName $ruleName `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort $ports `
            -Profile Any | Out-Null
        Write-Host "Firewall allowed TCP ports: $($ports -join ', ')"
    } catch {
        Write-Host "WARN Firewall rule was not updated: $($_.Exception.Message)"
    }
}

function Start-UvicornIfNeeded {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$ServiceDir,
        [Parameter(Mandatory = $true)]
        [string]$VenvPython,
        [Parameter(Mandatory = $true)]
        [string]$LogName,
        [Parameter(Mandatory = $true)]
        [hashtable]$Environment
    )

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        Write-Host "Port $Port already listening. PID: $($listener.OwningProcess)"
        return
    }

    $scriptPath = Join-Path $env:TEMP "meeting-agent-start-$Port.ps1"
    $envLines = foreach ($entry in $Environment.GetEnumerator()) {
        "`$env:$($entry.Key) = '$($entry.Value -replace "'", "''")'"
    }

    @(
        '$ErrorActionPreference = ''Stop'''
        $envLines
        "Set-Location '$($ServiceDir -replace "'", "''")'"
        "'Starting Uvicorn on port $Port'"
        "'DATABASE_URL=' + `$env:DATABASE_URL"
        "'STORAGE_DIR=' + `$env:STORAGE_DIR"
        "& '$($VenvPython -replace "'", "''")' -m uvicorn app.main:app --host 0.0.0.0 --port $Port"
    ) | Set-Content -Path $scriptPath -Encoding UTF8

    Start-Process powershell -WindowStyle Hidden `
        -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $scriptPath `
        -RedirectStandardOutput (Join-Path $ServiceDir $LogName) `
        -RedirectStandardError (Join-Path $ServiceDir ($LogName -replace '\.log$', '.err.log'))
}

function Restart-ExpoServer {
    $listeners = Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Seconds 2

    $expoScript = Join-Path $env:TEMP 'meeting-agent-start-expo.ps1'
    @(
        '$ErrorActionPreference = ''Stop'''
        "Set-Location '$($MobileDir -replace "'", "''")'"
        "`$env:REACT_NATIVE_PACKAGER_HOSTNAME = '$HostIp'"
        "npx expo start --$ExpoHostMode --clear"
    ) | Set-Content -Path $expoScript -Encoding UTF8

    Start-Process powershell -WindowStyle Hidden `
        -WorkingDirectory $MobileDir `
        -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $expoScript `
        -RedirectStandardOutput (Join-Path $MobileDir 'expo.log') `
        -RedirectStandardError (Join-Path $MobileDir 'expo.err.log')
}

function Get-ExpoManifest {
    $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8081/.expo/packager-info' -TimeoutSec 10
    return $response.Content | ConvertFrom-Json
}

function Wait-ExpoTunnelManifest {
    param(
        [int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $manifest = Get-ExpoManifest
            $hostUri = $manifest.extra.expoClient.hostUri
            if ($hostUri -and $hostUri -like '*.exp.direct') {
                Write-Host "OK Expo tunnel host: $hostUri"
                return $manifest
            }
        } catch {
            # Expo writes packager-info after Metro is ready.
        }
        Start-Sleep -Seconds 2
    }

    throw 'Timed out waiting for Expo tunnel hostUri in packager-info.'
}

function Wait-HttpOk {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                Write-Host "OK $Url"
                return
            }
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for $Url. Last error: $lastError"
}

if (-not $HostIp) {
    $HostIp = Get-LocalHostIp
}

Enable-LocalFirewallPorts
Import-ProjectEnv -ProjectRoot $ProjectRoot

$rawDatabaseUrl = $env:DATABASE_URL
if (-not $rawDatabaseUrl) {
    $rawDatabaseUrl = 'postgresql+psycopg://meeting_agent:meeting_agent@127.0.0.1:5432/meeting_agent'
}
$databaseUrl = Convert-LocalDatabaseUrl $rawDatabaseUrl

$storageDir = $env:STORAGE_DIR
if (-not $storageDir) {
    $storageDir = Join-Path $ProjectRoot 'storage'
}

$ollamaModel = $env:OLLAMA_MODEL
if (-not $ollamaModel) {
    $ollamaModel = 'qwen3:14b'
}

$ollamaBaseUrl = $env:OLLAMA_BASE_URL
if (-not $ollamaBaseUrl) {
    $ollamaBaseUrl = 'http://127.0.0.1:11434'
}

$workerUrl = "http://$HostIp`:8001"
$apiBaseUrl = "http://$HostIp`:8081/api-proxy"

if ($ExpoHostMode -eq 'tunnel') {
    $settingsPath = Join-Path $MobileDir '.expo\settings.json'
    $appJsonPath = Join-Path $MobileDir 'app.json'
    $urlRandomness = $null
    $owner = $null

    if (Test-Path $settingsPath) {
        $settings = Get-Content $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $urlRandomness = $settings.urlRandomness
    }
    if (Test-Path $appJsonPath) {
        $appConfig = Get-Content $appJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $owner = $appConfig.expo.owner
    }
    if ($urlRandomness -and $owner) {
        $predictedTunnelHost = "$($urlRandomness.ToLowerInvariant())-$owner-8081.exp.direct"
        $apiBaseUrl = "https://$predictedTunnelHost/api-proxy"
        Write-Host "Predicted Expo tunnel API: $apiBaseUrl"
    }
}

Set-MobileEnvValue -Name 'EXPO_PUBLIC_API_BASE_URL' -Value $apiBaseUrl

Start-UvicornIfNeeded -Port 8001 `
    -ServiceDir $WorkerDir `
    -VenvPython (Join-Path $WorkerDir '.venv\Scripts\python.exe') `
    -LogName 'worker-local.log' `
    -Environment @{
        DATABASE_URL = $databaseUrl
        STORAGE_DIR = $storageDir
        OLLAMA_MODEL = $ollamaModel
        OLLAMA_BASE_URL = $ollamaBaseUrl
        HF_HUB_OFFLINE = '1'
        TRANSFORMERS_OFFLINE = '1'
    }

Start-Sleep -Seconds 4

Start-UvicornIfNeeded -Port 8002 `
    -ServiceDir $ApiDir `
    -VenvPython (Join-Path $ApiDir '.venv\Scripts\python.exe') `
    -LogName 'api-local.log' `
    -Environment @{
        DATABASE_URL = $databaseUrl
        STORAGE_DIR = $storageDir
        WORKER_URL = $workerUrl
        API_CORS_ORIGINS = '*'
        AGENT_LOCAL_AUTH_ENABLED = 'false'
        AGENT_LOCAL_AUTH_TENANT_ID = 'default-tenant'
        AGENT_LOCAL_AUTH_PROJECT_ID = 'default-project'
    }

Restart-ExpoServer
Start-Sleep -Seconds 5

$metroStatusUrl = "http://$HostIp`:8081/status"
$iosBundleUrl = "http://$HostIp`:8081/node_modules/expo/AppEntry.bundle?platform=ios&dev=true&hot=false&lazy=true&transform.engine=hermes&transform.bytecode=1&transform.routerRoot=app&unstable_transformProfile=hermes-stable"
$apiHealthUrl = "http://$HostIp`:8002/health"

if ($ExpoHostMode -eq 'tunnel') {
    Wait-HttpOk -Url 'http://127.0.0.1:8081/status' -TimeoutSeconds 90
    $manifest = Wait-ExpoTunnelManifest -TimeoutSeconds 90
    $hostUri = $manifest.extra.expoClient.hostUri
    Set-MobileEnvValue -Name 'EXPO_PUBLIC_API_BASE_URL' -Value "https://$hostUri/api-proxy"

    $tunnelBundleUrl = "http://$hostUri/node_modules/expo/AppEntry.bundle?platform=ios&dev=true&hot=false&lazy=true&transform.engine=hermes&transform.bytecode=1&transform.routerRoot=app&unstable_transformProfile=hermes-stable"
    $tunnelApiHealthUrl = "https://$hostUri/api-proxy/health"
    Wait-HttpOk -Url $tunnelBundleUrl -TimeoutSeconds 120
    Wait-HttpOk -Url $tunnelApiHealthUrl -TimeoutSeconds 30
} else {
    Set-MobileEnvValue -Name 'EXPO_PUBLIC_API_BASE_URL' -Value "http://$HostIp`:8081/api-proxy"
    Wait-HttpOk -Url $metroStatusUrl -TimeoutSeconds 90
    Wait-HttpOk -Url $iosBundleUrl -TimeoutSeconds 120
    Wait-HttpOk -Url "http://$HostIp`:8081/api-proxy/health" -TimeoutSeconds 30
}
Wait-HttpOk -Url $apiHealthUrl -TimeoutSeconds 30

$qrUri = "exp://$HostIp`:8081"
if ($ExpoHostMode -eq 'tunnel') {
    $manifest = Wait-ExpoTunnelManifest -TimeoutSeconds 30
    $hostUri = $manifest.extra.expoClient.hostUri
    if (-not $hostUri) {
        throw 'Expo tunnel hostUri was not found in packager-info.'
    }
    $qrUri = "exp://$hostUri"
}
Push-Location $ProjectRoot
try {
    @"
import qrcode
uris = {
    "expo-go-current-qr.png": "$qrUri",
    "expo-http-current-qr.png": "http://$HostIp`:8081",
    "expo-go-192-168-1-6-qr.png": "exp://192.168.1.6:8081",
    "expo-go-192-168-1-7-qr.png": "exp://192.168.1.7:8081",
}
for filename, uri in uris.items():
    img = qrcode.make(uri)
    img.save(f"apps/mobile/{filename}")
print("$qrUri")
"@ | & (Join-Path $ApiDir '.venv\Scripts\python.exe') -
} finally {
    Pop-Location
}

Write-Host "Mobile API: $apiBaseUrl"
Write-Host "Expo URL: $qrUri"
Write-Host "Expo QR: $(Join-Path $MobileDir 'expo-go-current-qr.png')"
