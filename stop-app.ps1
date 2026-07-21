$project = 'C:\Users\Jagan Raj\Projects\inventory-app'
$pidFile = "$project\.run\pids.json"

Write-Host "Stopping Inventory App services..."

Get-Process InventoryApp,electron -ErrorAction SilentlyContinue | Stop-Process -Force

if (Test-Path $pidFile) {
  $p = Get-Content $pidFile -Raw | ConvertFrom-Json
  if ($p.backend_pid) { cmd /c "taskkill /PID $($p.backend_pid) /F /T" | Out-Null }
  if ($p.frontend_pid) { cmd /c "taskkill /PID $($p.frontend_pid) /F /T" | Out-Null }
  Remove-Item $pidFile -Force
}

function Stop-ListeningPort {
  param([int]$Port)
  $lines = cmd /c "netstat -ano | findstr LISTENING | findstr :$Port"
  foreach ($line in ($lines -split "`r?`n")) {
    if ($line -match '\s(\d+)\s*$') {
      $pid = [int]$Matches[1]
      if ($pid -gt 0) { cmd /c "taskkill /PID $pid /F /T" | Out-Null }
    }
  }
}

Stop-ListeningPort 5173
Stop-ListeningPort 8000

Write-Host "Stopped app, frontend, backend."
Write-Host "Docker DB still running. To stop DB: cd '$project'; docker compose down"