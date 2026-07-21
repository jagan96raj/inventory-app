$project = 'C:\Users\Jagan Raj\Projects\inventory-app'
$backend = "$project\backend"
$frontend = "$project\frontend"
$uvicorn = "$backend\.venv\Scripts\uvicorn.exe"
$npm = (Get-Command npm.cmd).Source
$runDir = "$project\.run"
$pidFile = "$runDir\pids.json"
$appExe = "$env:LOCALAPPDATA\Programs\InventoryApp\InventoryApp.exe"

New-Item -ItemType Directory -Force -Path $runDir | Out-Null

Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 12

Start-Process -FilePath "docker" -ArgumentList "compose","up","-d" -WorkingDirectory $project -WindowStyle Hidden | Out-Null
Start-Sleep -Seconds 5

$backendProc = Start-Process -FilePath $uvicorn -ArgumentList "app.main:app","--reload","--host","127.0.0.1","--port","8000" -WorkingDirectory $backend -PassThru
Start-Sleep -Seconds 3

$frontendProc = Start-Process -FilePath $npm -ArgumentList "run","dev","--","--host","127.0.0.1","--port","5173" -WorkingDirectory $frontend -PassThru

@{
  backend_pid = $backendProc.Id
  frontend_pid = $frontendProc.Id
  started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -Encoding UTF8 $pidFile

$ready = $false
for ($i = 0; $i -lt 40; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -ge 200) { $ready = $true; break }
  } catch {}
  Start-Sleep -Seconds 2
}

if ($ready -and (Test-Path $appExe)) {
  Start-Process $appExe
} else {
  Write-Host "Frontend not ready yet. Open InventoryApp manually after 1 minute."
}