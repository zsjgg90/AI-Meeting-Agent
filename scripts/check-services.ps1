param(
    [string]$ApiBaseUrl = 'http://127.0.0.1:8000',
    [string]$WorkerBaseUrl = 'http://127.0.0.1:8001',
    [string]$OllamaBaseUrl = 'http://127.0.0.1:11434',
    [string]$ExpectedOllamaModel = 'qwen3:14b'
)

$ErrorActionPreference = 'Continue'
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$Failures = 0

function Write-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [string]$Detail = '',
        [switch]$Optional
    )

    $prefix = if ($Ok) { 'OK' } elseif ($Optional) { 'WARN' } else { 'FAIL' }
    Write-Host "$prefix $Name $Detail"
    if (-not $Ok -and -not $Optional) {
        $script:Failures += 1
    }
}

function Test-Port {
    param(
        [string]$Name,
        [int]$Port,
        [switch]$Optional
    )

    try {
        $connection = Test-NetConnection -ComputerName '127.0.0.1' -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
        Write-Check -Name "$Name port $Port" -Ok ([bool]$connection) -Optional:$Optional
    }
    catch {
        Write-Check -Name "$Name port $Port" -Ok $false -Detail $_.Exception.Message -Optional:$Optional
    }
}

function Test-PortOwner {
    param(
        [string]$Name,
        [int]$Port,
        [string]$ExpectedPath
    )

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) {
        Write-Check -Name "$Name port owner" -Ok $false -Detail "port $Port is not listening"
        return
    }

    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    $actualPath = if ($owner) { $owner.Path } else { '' }
    $ownerInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $parent = if ($ownerInfo) { Get-Process -Id $ownerInfo.ParentProcessId -ErrorAction SilentlyContinue } else { $null }
    $parentPath = if ($parent) { $parent.Path } else { '' }
    $ok = ($actualPath -ieq $ExpectedPath) -or ($parentPath -ieq $ExpectedPath)
    Write-Check -Name "$Name port owner" -Ok $ok -Detail "pid=$($listener.OwningProcess) path=$actualPath parent=$parentPath"
}

function Test-Http {
    param(
        [string]$Name,
        [string]$Url,
        [switch]$Optional
    )

    try {
        $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 5 -ErrorAction Stop
        $isOk = $true
        if ($null -ne $response.status -and $response.status -eq 'error') {
            $isOk = $false
        }
        Write-Check -Name $Name -Ok $isOk -Detail ($response | ConvertTo-Json -Compress) -Optional:$Optional
    }
    catch {
        Write-Check -Name $Name -Ok $false -Detail $_.Exception.Message -Optional:$Optional
    }
}

Set-Location $ProjectRoot

Write-Host "ProjectRoot=$ProjectRoot"

Test-Port -Name 'PostgreSQL' -Port 5432
Test-Port -Name 'Redis' -Port 6379 -Optional
Test-Port -Name 'Ollama' -Port 11434
Test-Port -Name 'Worker' -Port 8001
Test-Port -Name 'API' -Port 8000
Test-Port -Name 'Expo Metro' -Port 8081 -Optional


Test-Http -Name 'API health' -Url "$ApiBaseUrl/health"
Test-Http -Name 'API ready' -Url "$ApiBaseUrl/ready"
Test-Http -Name 'Worker health' -Url "$WorkerBaseUrl/health"
Test-Http -Name 'Worker ready' -Url "$WorkerBaseUrl/ready"

try {
    $models = Invoke-RestMethod -Uri "$($OllamaBaseUrl.TrimEnd('/'))/api/tags" -Method Get -TimeoutSec 5 -ErrorAction Stop
    $names = @($models.models | ForEach-Object { $_.name })
    Write-Check -Name 'Ollama model' -Ok ($names -contains $ExpectedOllamaModel) -Detail "expected=$ExpectedOllamaModel available=$($names -join ',')"
}
catch {
    Write-Check -Name 'Ollama model' -Ok $false -Detail $_.Exception.Message
}

$PromptFile = Join-Path $ProjectRoot 'services\worker\app\prompts\meeting_analyst_qwen3.md'
$RagManifest = Join-Path $ProjectRoot 'data\rag\meeting_analyst_rag_manifest.json'
$VectorDir = Join-Path $ProjectRoot 'data\vector_db'

Write-Check -Name 'Prompt file' -Ok (Test-Path $PromptFile) -Detail $PromptFile
Write-Check -Name 'RAG manifest' -Ok (Test-Path $RagManifest) -Detail $RagManifest
Write-Check -Name 'Vector DB dir' -Ok (Test-Path $VectorDir) -Detail $VectorDir

try {
    $ApiAlembic = Join-Path $ProjectRoot 'services\api\.venv\Scripts\alembic.exe'
    if (Test-Path $ApiAlembic) {
        Push-Location (Join-Path $ProjectRoot 'services\api')
        try {
            & $ApiAlembic heads
            Write-Check -Name 'Alembic heads command' -Ok ($LASTEXITCODE -eq 0)
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Check -Name 'Alembic executable' -Ok $false -Detail $ApiAlembic
    }
}
catch {
    Write-Check -Name 'Alembic heads command' -Ok $false -Detail $_.Exception.Message
}

if ($Failures -gt 0) {
    Write-Host ""
    Write-Host "Service check failed: $Failures critical check(s)."
    exit 1
}

Write-Host ""
Write-Host 'Service check passed.'
