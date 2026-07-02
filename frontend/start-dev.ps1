# Start Vite without requiring node/npm on PATH
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path "node_modules\vite\bin\vite.js")) {
    Write-Host "Missing node_modules. Run from a terminal where npm works:" -ForegroundColor Yellow
    Write-Host '  & "C:\Program Files\nodejs\npm.cmd" install' -ForegroundColor Yellow
    exit 1
}

function Find-NodeExe {
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = @(
        "$env:ProgramFiles\nodejs\node.exe",
        "${env:ProgramFiles(x86)}\nodejs\node.exe",
        "$env:LOCALAPPDATA\Programs\cursor\resources\app\resources\helpers\node.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

$nodeExe = Find-NodeExe
if (-not $nodeExe) {
    Write-Host "Node.js not found." -ForegroundColor Red
    Write-Host "Install LTS from https://nodejs.org/ and restart PowerShell." -ForegroundColor Yellow
    Write-Host "Or run once:" -ForegroundColor Yellow
    Write-Host '  & "C:\Program Files\nodejs\node.exe" .\node_modules\vite\bin\vite.js' -ForegroundColor Cyan
    exit 1
}

Write-Host "Using: $nodeExe" -ForegroundColor DarkGray
Write-Host "Starting frontend at http://localhost:5173/ ..." -ForegroundColor Green
& $nodeExe .\node_modules\vite\bin\vite.js
