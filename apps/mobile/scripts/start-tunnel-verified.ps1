param(
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$MobileRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$ProjectRoot = Resolve-Path (Join-Path $MobileRoot '..\..')
$QrPath = Join-Path $MobileRoot 'expo-go-current-qr.png'

function Wait-HttpOk {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 20
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                Write-Host "OK $Url"
                return $response
            }
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 3
    }

    throw "Timed out waiting for $Url. Last error: $lastError"
}

function Get-PackagerInfo {
    $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8081/.expo/packager-info' -TimeoutSec 10
    return $response.Content | ConvertFrom-Json
}

function Wait-TunnelHost {
    param([int]$TimeoutSeconds = 120)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $info = Get-PackagerInfo
            $hostUri = $info.extra.expoClient.hostUri
            if ($hostUri -and $hostUri -like '*.exp.direct') {
                Write-Host "Tunnel host: $hostUri"
                return $hostUri
            }
        } catch {
            # Metro may not have written packager-info yet.
        }
        Start-Sleep -Seconds 3
    }

    throw 'Expo tunnel did not become ready with an exp.direct host.'
}

Set-Location $MobileRoot
Remove-Item -Recurse -Force '.expo' -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force 'node_modules\.cache' -ErrorAction SilentlyContinue
Remove-Item 'expo.log', 'expo.err.log' -ErrorAction SilentlyContinue

$listener = Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

Start-Process cmd.exe -WindowStyle Hidden -WorkingDirectory $MobileRoot -ArgumentList '/c npx expo start --tunnel --clear > expo.log 2> expo.err.log'

Wait-HttpOk -Url 'http://127.0.0.1:8081/status' -TimeoutSeconds $TimeoutSeconds | Out-Null
$hostUri = Wait-TunnelHost -TimeoutSeconds $TimeoutSeconds

$bundleUrl = "http://$hostUri/node_modules/expo/AppEntry.bundle?platform=ios&dev=true&hot=false&lazy=true&transform.engine=hermes&transform.bytecode=1&transform.routerRoot=app&unstable_transformProfile=hermes-stable"
$apiHealthUrl = "https://$hostUri/api-proxy/health"
$meetingsUrl = "https://$hostUri/api-proxy/meetings?limit=50&offset=0"

Wait-HttpOk -Url $bundleUrl -TimeoutSeconds $TimeoutSeconds | Out-Null
Wait-HttpOk -Url $apiHealthUrl -TimeoutSeconds 60 | Out-Null
Wait-HttpOk -Url $meetingsUrl -TimeoutSeconds 60 | Out-Null

$qrUri = "exp://$hostUri"
Push-Location $MobileRoot
try {
    @"
import qrcode
img = qrcode.make("$qrUri")
img.save("expo-go-current-qr.png")
print("$qrUri")
"@ | & (Join-Path $ProjectRoot 'services\api\.venv\Scripts\python.exe') -
} finally {
    Pop-Location
}

Write-Host "Expo tunnel verified: $qrUri"
Write-Host "API through tunnel verified: $apiHealthUrl"
Write-Host "QR: $QrPath"
