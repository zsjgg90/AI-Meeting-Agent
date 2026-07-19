$ErrorActionPreference = 'Stop'

function Import-ProjectEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $envPath = Join-Path $ProjectRoot '.env'
    if (-not (Test-Path $envPath)) {
        return
    }

    Get-Content $envPath -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#') -or -not $line.Contains('=')) {
            return
        }

        $parts = $line.Split('=', 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")

        if ($name -and -not [Environment]::GetEnvironmentVariable($name, 'Process')) {
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

function Set-EnvDefault {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if (-not [Environment]::GetEnvironmentVariable($Name, 'Process')) {
        [Environment]::SetEnvironmentVariable($Name, $Value, 'Process')
    }
}

function Convert-LocalDatabaseUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DatabaseUrl
    )

    return $DatabaseUrl -replace '@(db|postgres|database):5432/', '@127.0.0.1:5432/'
}

function Convert-LocalWorkerUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkerUrl
    )

    return $WorkerUrl -replace '://(worker|api-worker)(:8001)?', '://127.0.0.1$2'
}
