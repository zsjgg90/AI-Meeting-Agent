$ErrorActionPreference = 'Stop'

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
. (Join-Path $ProjectRoot 'scripts\local-env.ps1')

Import-ProjectEnv -ProjectRoot $ProjectRoot
Set-EnvDefault -Name 'DATABASE_URL' -Value 'postgresql+psycopg://meeting_agent:meeting_agent@127.0.0.1:5432/meeting_agent'
Set-EnvDefault -Name 'STORAGE_DIR' -Value (Join-Path $ProjectRoot 'storage')
Set-EnvDefault -Name 'OLLAMA_MODEL' -Value 'qwen3:14b'
Set-EnvDefault -Name 'OLLAMA_BASE_URL' -Value 'http://127.0.0.1:11434'
Set-EnvDefault -Name 'HF_HUB_OFFLINE' -Value '1'
Set-EnvDefault -Name 'TRANSFORMERS_OFFLINE' -Value '1'

$env:DATABASE_URL = Convert-LocalDatabaseUrl $env:DATABASE_URL

$port = 8001
$expectedPython = Resolve-Path (Join-Path $ProjectRoot 'services\worker\.venv\Scripts\python.exe')
$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    $ownerInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $parent = if ($ownerInfo) { Get-Process -Id $ownerInfo.ParentProcessId -ErrorAction SilentlyContinue } else { $null }
    $isProjectProcess = ($null -ne $owner -and $owner.Path -ieq $expectedPython.Path) -or ($null -ne $parent -and $parent.Path -ieq $expectedPython.Path)
    if (-not $isProjectProcess) {
        Write-Error "Port $port is already owned by a non-project Worker process. PID=$($listener.OwningProcess) Path=$($owner.Path). Stop it before starting the local Worker."
        exit 1
    }
    Write-Host "Worker already listening on port $port from project venv. PID: $($listener.OwningProcess)"
    Write-Host 'No new Worker process was started.'
    exit 0
}

Set-Location (Join-Path $ProjectRoot 'services\worker')

Write-Host "Starting Worker on http://0.0.0.0:$port"
Write-Host "DATABASE_URL=$env:DATABASE_URL"
Write-Host "OLLAMA_MODEL=$env:OLLAMA_MODEL"
Write-Host "OLLAMA_BASE_URL=$env:OLLAMA_BASE_URL"
Write-Host "HF_HUB_OFFLINE=$env:HF_HUB_OFFLINE"
Write-Host "TRANSFORMERS_OFFLINE=$env:TRANSFORMERS_OFFLINE"
Write-Host "Logs are printed to this console. Look for [ANALYST] and [OLLAMA] Calling model: $env:OLLAMA_MODEL."
Write-Host 'Optional file logging: append "2>&1 | Tee-Object -FilePath worker-local.log" when running this command manually.'

.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port $port
