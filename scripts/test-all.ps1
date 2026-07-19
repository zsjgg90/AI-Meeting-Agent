param(
    [switch]$SkipMobile,
    [switch]$SkipApiTests,
    [switch]$SkipWorkerTests,
    [switch]$Health,
    [string]$ApiBaseUrl = 'http://127.0.0.1:8002',
    [string]$WorkerBaseUrl = 'http://127.0.0.1:8001'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$ApiPython = Join-Path $ProjectRoot 'services\api\.venv\Scripts\python.exe'
$WorkerPython = Join-Path $ProjectRoot 'services\worker\.venv\Scripts\python.exe'
$MobileDir = Join-Path $ProjectRoot 'apps\mobile'

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host "==> $Message"
}

function Assert-File {
    param(
        [string]$Path,
        [string]$Message
    )

    if (-not (Test-Path $Path)) {
        throw "$Message Missing path: $Path"
    }
}

function Invoke-HealthCheck {
    param(
        [string]$Name,
        [string]$Url
    )

    try {
        Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 5 -ErrorAction Stop | Out-Null
        Write-Host "OK $Name $Url"
    }
    catch {
        throw "$Name health check failed: $Url"
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

Set-Location $ProjectRoot

Assert-File -Path $ApiPython -Message 'API virtual environment is not ready.'
Assert-File -Path $WorkerPython -Message 'Worker virtual environment is not ready.'

Write-Step 'Python compile: services/api/app'
Invoke-Checked { & $ApiPython -m compileall -q (Join-Path $ProjectRoot 'services\api\app') }

Write-Step 'Python compile: services/worker/app'
Invoke-Checked { & $WorkerPython -m compileall -q (Join-Path $ProjectRoot 'services\worker\app') }

$env:PYTHONPATH = "$ProjectRoot;$(Join-Path $ProjectRoot 'services\api');$(Join-Path $ProjectRoot 'services\worker');$($env:PYTHONPATH)"

if (-not $SkipApiTests) {
    Write-Step 'API contract tests'
    Invoke-Checked { & $ApiPython -m unittest `
        services.api.tests.test_api_contract `
        services.api.tests.test_agent_config }
}

if (-not $SkipWorkerTests) {
    Write-Step 'Worker unit tests'
    Invoke-Checked { & $WorkerPython -m unittest `
        services.worker.tests.test_worker_contract `
        services.worker.tests.test_observability `
        services.worker.tests.test_regression_fixtures `
        services.worker.tests.test_meeting_analyst_pipeline `
        services.worker.tests.test_meeting_analyst_service_fake `
        services.worker.tests.test_prompt_rag_versioning `
        services.worker.tests.test_agent_config `
        services.worker.tests.test_agent_contract `
        services.worker.tests.test_meeting_scenarios `
        services.worker.tests.test_agent_tools_contract `
        services.worker.tests.test_agent_tools_adapters `
        services.worker.tests.test_volcengine_speaker_diarization }
}

if (-not $SkipMobile) {
    Write-Step 'Mobile TypeScript typecheck'
    Assert-File -Path (Join-Path $MobileDir 'package.json') -Message 'Mobile app is not ready.'
    Push-Location $MobileDir
    try {
        Invoke-Checked { npm run typecheck }
    }
    finally {
        Pop-Location
    }
}

if ($Health) {
    Write-Step 'Local service health checks'
    Invoke-HealthCheck -Name 'API' -Url "$ApiBaseUrl/health"
    Invoke-HealthCheck -Name 'API readiness' -Url "$ApiBaseUrl/ready"
    Invoke-HealthCheck -Name 'Worker' -Url "$WorkerBaseUrl/health"
    Invoke-HealthCheck -Name 'Worker readiness' -Url "$WorkerBaseUrl/ready"
}

Write-Host ''
Write-Host 'All selected checks passed.'
