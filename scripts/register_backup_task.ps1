# Spec v16.0.8 — register Windows Scheduled Task for daily backup.
# Run PowerShell as Administrator once to register.
#Requires -Version 5.1

param(
    [string]$Password
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "backup-common.ps1")

$taskName = "InventoryApp-DailyBackup"

try {
    $repoRoot = Get-RepoRoot
    $cfg = Get-BackupConfig -RepoRoot $repoRoot
    $backupScript = Join-Path $PSScriptRoot "backup_db.ps1"

    if (-not (Test-Path $backupScript)) {
        throw "backup_db.ps1 not found at $backupScript"
    }

    $timeText = $cfg.ScheduleTime.Trim()
    if ($timeText -notmatch '^(\d{1,2}):(\d{2})$') {
        throw "Invalid BACKUP_SCHEDULE_TIME '$timeText'. Use HH:mm (e.g. 02:00)."
    }
    $hour = [int]$matches[1]
    $minute = [int]$matches[2]
    if ($hour -lt 0 -or $hour -gt 23 -or $minute -lt 0 -or $minute -gt 59) {
        throw "Invalid BACKUP_SCHEDULE_TIME '$timeText'. Hour must be 0-23, minute 0-59."
    }
    $atTime = Get-Date -Hour $hour -Minute $minute -Second 0

    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`"" `
        -WorkingDirectory $repoRoot

    $trigger = New-ScheduledTaskTrigger -Daily -At $atTime

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -DontStopIfGoingOnBatteries `
        -AllowStartIfOnBatteries

    $userId = "$env:USERDOMAIN\$env:USERNAME"

    if ($Password) {
        $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Password -RunLevel Highest
        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Principal $principal `
            -Settings $settings `
            -Description "Daily PostgreSQL backup for Inventory App (Spec v16.0.8)" `
            -Force | Out-Null
        # Set password via schtasks (Register-ScheduledTask -Password is not always available)
        & schtasks.exe /Change /TN $taskName /RP $Password | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to set task password. Verify the account password."
        }
        $logonNote = "Runs whether you are logged on or not (stored credentials)."
    }
    else {
        $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Highest
        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Principal $principal `
            -Settings $settings `
            -Description "Daily PostgreSQL backup for Inventory App (Spec v16.0.8)" `
            -Force | Out-Null
        $logonNote = "Runs when you are logged on (Docker Desktop must be running)."
    }

    Write-Host ""
    Write-Host "Scheduled task registered: $taskName" -ForegroundColor Green
    Write-Host "  Schedule: daily at $($atTime.ToString('HH:mm'))" -ForegroundColor Cyan
    Write-Host "  Script:   $backupScript" -ForegroundColor Cyan
    Write-Host "  Backup:   $($cfg.BackupDir)" -ForegroundColor Cyan
    Write-Host "  Account:  $userId ($logonNote)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Verify in Task Scheduler (taskschd.msc) -> Task Scheduler Library -> $taskName" -ForegroundColor Yellow
    Write-Host "Test now:  Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Tip: For overnight backups while logged off, re-run this script as Administrator with -Password." -ForegroundColor DarkGray
    Write-Host "     Docker Desktop must be running or set to start at Windows login." -ForegroundColor DarkGray

    exit 0
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Run this script in an elevated PowerShell (Run as Administrator)." -ForegroundColor Yellow
    exit 1
}
