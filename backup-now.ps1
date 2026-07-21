$project = 'C:\Users\Jagan Raj\Projects\inventory-app'
$backupScript = "$project\scripts\backup_db.ps1"

Write-Host "Starting database backup..." -ForegroundColor Cyan

# Ensure Docker + DB are up
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 8
Start-Process -FilePath "docker" -ArgumentList "compose","up","-d" -WorkingDirectory $project -WindowStyle Hidden | Out-Null
Start-Sleep -Seconds 5

# Run existing backup script
powershell -ExecutionPolicy Bypass -File $backupScript
$code = $LASTEXITCODE

if ($code -eq 0) {
  Write-Host "Backup completed successfully." -ForegroundColor Green
  $backupDir = (Select-String -Path "$project\.env" -Pattern '^BACKUP_DIR=(.+)$').Matches.Groups[1].Value
  if ($backupDir -and (Test-Path $backupDir)) {
    Start-Process explorer.exe $backupDir
  }
} else {
  Write-Host "Backup failed. Check Docker is running." -ForegroundColor Red
}

Read-Host "Press Enter to close"