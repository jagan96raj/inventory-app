# Spec v16.0.8 — daily PostgreSQL backup (pg_dump via Docker).
# Run from repo root or anywhere; resolves repo via script location.
#Requires -Version 5.1

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "backup-common.ps1")

try {
    $repoRoot = Get-RepoRoot
    Set-Location $repoRoot

    $cfg = Get-BackupConfig -RepoRoot $repoRoot
    $containerId = Test-DockerDbRunning -RepoRoot $repoRoot

    if (-not (Test-Path $cfg.BackupDir)) {
        New-Item -ItemType Directory -Path $cfg.BackupDir -Force | Out-Null
        Write-Host "Created backup directory: $($cfg.BackupDir)" -ForegroundColor DarkGray
    }

    $timestamp = Get-Date -Format "yyyy-MM-dd_HHmm"
    $outFile = Join-Path $cfg.BackupDir "inventory-$timestamp.dump"
    $containerTmp = "/tmp/inventory-backup-$timestamp.dump"

    Write-Host "Backing up database '$($cfg.PostgresDb)' as user '$($cfg.PostgresUser)'..." -ForegroundColor Cyan

    docker compose exec -T db pg_dump -U $cfg.PostgresUser -Fc -f $containerTmp $cfg.PostgresDb 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed. Check Postgres logs: docker compose logs db"
    }

    docker cp "${containerId}:${containerTmp}" $outFile 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy backup from container to $outFile"
    }

    docker compose exec -T db rm -f $containerTmp 2>&1 | Out-Null

    if (-not (Test-Path $outFile)) {
        throw "Backup file was not created: $outFile"
    }

    $size = (Get-Item $outFile).Length
    Write-Host "Backup saved: $outFile ($(Format-FileSize $size))" -ForegroundColor Green

    if ($cfg.RetentionDays -gt 0) {
        $cutoff = (Get-Date).AddDays(-$cfg.RetentionDays)
        $removed = 0
        Get-ChildItem -Path $cfg.BackupDir -Filter "*.dump" -File | ForEach-Object {
            if ($_.LastWriteTime -lt $cutoff) {
                Remove-Item -LiteralPath $_.FullName -Force
                $removed++
                Write-Host "Removed old backup: $($_.Name)" -ForegroundColor DarkGray
            }
        }
        if ($removed -gt 0) {
            Write-Host "Retention: removed $removed file(s) older than $($cfg.RetentionDays) days." -ForegroundColor DarkGray
        }
    }

    exit 0
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Ensure Docker Desktop is running and Postgres is up: docker compose up -d" -ForegroundColor Yellow
    exit 1
}
