# Spec v16.0.8 — restore PostgreSQL from a pg_dump custom-format (.dump) backup.
# WARNING: Overwrites data in the target database. Dev / disaster recovery only.
#Requires -Version 5.1

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$BackupFile,

    [switch]$Force
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "backup-common.ps1")

Write-Host ""
Write-Host "================================================================" -ForegroundColor Red
Write-Host " WARNING: DESTRUCTIVE RESTORE" -ForegroundColor Red
Write-Host " This replaces ALL data in the Postgres database with the backup." -ForegroundColor Red
Write-Host " Use only on a dev copy or after a confirmed disaster." -ForegroundColor Red
Write-Host " Stop the backend (uvicorn) before restoring." -ForegroundColor Red
Write-Host "================================================================" -ForegroundColor Red
Write-Host ""

try {
    $repoRoot = Get-RepoRoot
    Set-Location $repoRoot

    $resolvedBackup = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($BackupFile)
    if (-not (Test-Path $resolvedBackup)) {
        throw "Backup file not found: $resolvedBackup"
    }

    $cfg = Get-BackupConfig -RepoRoot $repoRoot
    $containerId = Test-DockerDbRunning -RepoRoot $repoRoot

    Write-Host "Target database : $($cfg.PostgresDb)" -ForegroundColor Cyan
    Write-Host "Backup file     : $resolvedBackup" -ForegroundColor Cyan
    Write-Host ""

    if (-not $Force) {
        $answer = Read-Host "Type RESTORE to continue"
        if ($answer -ne "RESTORE") {
            Write-Host "Aborted." -ForegroundColor Yellow
            exit 1
        }
    }

    $containerBackup = "/tmp/inventory-restore.dump"
    Write-Host "Copying backup into container..." -ForegroundColor Cyan
    docker cp $resolvedBackup "${containerId}:${containerBackup}" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "docker cp failed"
    }

    Write-Host "Terminating active connections..." -ForegroundColor Cyan
    $terminateSql = @"
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$($cfg.PostgresDb)' AND pid <> pg_backend_pid();
"@
    docker compose exec -T db psql -U $cfg.PostgresUser -d postgres -v ON_ERROR_STOP=1 -c $terminateSql 2>&1 | Out-Null

    Write-Host "Dropping and recreating database '$($cfg.PostgresDb)'..." -ForegroundColor Cyan
    docker compose exec -T db psql -U $cfg.PostgresUser -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $($cfg.PostgresDb);" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "DROP DATABASE failed"
    }
    docker compose exec -T db psql -U $cfg.PostgresUser -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $($cfg.PostgresDb);" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "CREATE DATABASE failed"
    }

    Write-Host "Restoring from backup (pg_restore)..." -ForegroundColor Cyan
    docker compose exec -T db pg_restore -U $cfg.PostgresUser -d $cfg.PostgresDb --no-owner --no-acl $containerBackup 2>&1 | ForEach-Object {
        if ($_ -match "error:") {
            Write-Host $_ -ForegroundColor Yellow
        }
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "pg_restore reported warnings or errors (often safe for role/ACL mismatches). Verify data after restore." -ForegroundColor Yellow
    }

    docker compose exec -T db rm -f $containerBackup 2>&1 | Out-Null

    Write-Host ""
    Write-Host "Restore complete." -ForegroundColor Green
    Write-Host "Next: cd backend; alembic upgrade head  (if schema drifted); restart backend." -ForegroundColor Cyan
    exit 0
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
