# Shared helpers for Spec v16.0.8 backup scripts.

function Get-RepoRoot {
    $root = Split-Path -Parent $PSScriptRoot
    $compose = Join-Path $root "docker-compose.yml"
    if (-not (Test-Path $compose)) {
        throw "docker-compose.yml not found at repo root: $root"
    }
    return $root
}

function Read-DotEnv {
    param([string]$Path)

    $result = @{}
    if (-not (Test-Path $Path)) {
        return $result
    }

    foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) {
            continue
        }
        $eq = $trimmed.IndexOf("=")
        if ($eq -lt 1) {
            continue
        }
        $key = $trimmed.Substring(0, $eq).Trim()
        $val = $trimmed.Substring($eq + 1).Trim()
        if ($val.Length -ge 2) {
            if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
                $val = $val.Substring(1, $val.Length - 2)
            }
        }
        $result[$key] = $val
    }
    return $result
}

function Get-BackupConfig {
    param([string]$RepoRoot)

    $envVars = Read-DotEnv -Path (Join-Path $RepoRoot ".env")
    $pgUser = if ($envVars["POSTGRES_USER"]) { $envVars["POSTGRES_USER"] } else { "inventory" }
    $pgDb = if ($envVars["POSTGRES_DB"]) { $envVars["POSTGRES_DB"] } else { "inventory" }
    $backupDir = if ($envVars["BACKUP_DIR"]) { $envVars["BACKUP_DIR"] } else { Join-Path $RepoRoot "backups" }
    $retentionDays = 30
    if ($envVars["BACKUP_RETENTION_DAYS"] -and $envVars["BACKUP_RETENTION_DAYS"] -ne "") {
        $retentionDays = [int]$envVars["BACKUP_RETENTION_DAYS"]
    }
    $scheduleTime = if ($envVars["BACKUP_SCHEDULE_TIME"]) { $envVars["BACKUP_SCHEDULE_TIME"] } else { "02:00" }

    return [PSCustomObject]@{
        PostgresUser     = $pgUser
        PostgresDb       = $pgDb
        BackupDir        = $backupDir
        RetentionDays    = $retentionDays
        ScheduleTime     = $scheduleTime
    }
}

function Test-DockerDbRunning {
    param([string]$RepoRoot)

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker not found on PATH. Install Docker Desktop and restart PowerShell."
    }

    Push-Location $RepoRoot
    try {
        $null = docker compose version 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose failed. Is Docker Desktop running?"
        }

        $containerId = (docker compose ps -q db 2>&1 | Out-String).Trim()
        if (-not $containerId) {
            throw "Postgres service 'db' is not running. Start it with: docker compose up -d"
        }

        $running = docker inspect -f "{{.State.Running}}" $containerId 2>&1
        if ($LASTEXITCODE -ne 0 -or $running -ne "true") {
            throw "Postgres container is not healthy. Run: docker compose up -d"
        }

        return $containerId
    }
    finally {
        Pop-Location
    }
}

function Format-FileSize {
    param([long]$Bytes)

    if ($Bytes -ge 1GB) {
        return "{0:N2} GB" -f ($Bytes / 1GB)
    }
    if ($Bytes -ge 1MB) {
        return "{0:N2} MB" -f ($Bytes / 1MB)
    }
    if ($Bytes -ge 1KB) {
        return "{0:N2} KB" -f ($Bytes / 1KB)
    }
    return "$Bytes bytes"
}
