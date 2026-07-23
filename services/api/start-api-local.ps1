$ErrorActionPreference = 'Stop'

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
. (Join-Path $ProjectRoot 'scripts\local-env.ps1')

Import-ProjectEnv -ProjectRoot $ProjectRoot
Set-EnvDefault -Name 'DATABASE_URL' -Value 'postgresql+psycopg://meeting_agent:meeting_agent@127.0.0.1:5432/meeting_agent'
Set-EnvDefault -Name 'STORAGE_DIR' -Value (Join-Path $ProjectRoot 'storage')
Set-EnvDefault -Name 'WORKER_URL' -Value 'http://127.0.0.1:8001'
Set-EnvDefault -Name 'API_CORS_ORIGINS' -Value '*'

$env:DATABASE_URL = Convert-LocalDatabaseUrl $env:DATABASE_URL
$env:WORKER_URL = Convert-LocalWorkerUrl $env:WORKER_URL

$port = 8002
$expectedPython = Resolve-Path (Join-Path $ProjectRoot 'services\api\.venv\Scripts\python.exe')
$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    $ownerInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $parent = if ($ownerInfo) { Get-Process -Id $ownerInfo.ParentProcessId -ErrorAction SilentlyContinue } else { $null }
    $isProjectProcess = ($null -ne $owner -and $owner.Path -ieq $expectedPython.Path) -or ($null -ne $parent -and $parent.Path -ieq $expectedPython.Path)
    if (-not $isProjectProcess) {
        Write-Error "Port $port is already owned by a non-project API process. PID=$($listener.OwningProcess) Path=$($owner.Path). Stop it before starting the local API."
        exit 1
    }
    Write-Host "API already listening on port $port from project venv. PID: $($listener.OwningProcess)"
    Write-Host 'No new API process was started.'
    exit 0
}

Set-Location (Join-Path $ProjectRoot 'services\api')

Write-Host "Starting API on http://0.0.0.0:$port"
Write-Host "DATABASE_URL=$env:DATABASE_URL"
Write-Host "WORKER_URL=$env:WORKER_URL"
if (-not $env:VOLCENGINE_ASR_API_KEY) {
    Write-Host 'VOLCENGINE_ASR_API_KEY is not configured. Realtime ASR will fail until it is set.'
}
Write-Host 'Logs are printed to this console.'
Write-Host 'Optional file logging: append "2>&1 | Tee-Object -FilePath api-local.log" when running this command manually.'

.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port $port
