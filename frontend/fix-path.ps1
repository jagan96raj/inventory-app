# Add Node.js to PATH for the current PowerShell session only
$nodeDir = "C:\Program Files\nodejs"
if (Test-Path "$nodeDir\node.exe") {
    $env:Path = "$nodeDir;$env:Path"
    Write-Host "Added Node.js to PATH for this session." -ForegroundColor Green
    Write-Host "node: $(node -v)"
    Write-Host "npm:  $(npm -v)"
    Write-Host ""
    Write-Host "Now run: npm run dev" -ForegroundColor Cyan
} else {
    Write-Host "Node.js not found at $nodeDir — install from https://nodejs.org/" -ForegroundColor Red
}
