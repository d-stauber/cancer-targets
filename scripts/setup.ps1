# One-shot setup for native Windows (PowerShell). Equivalent of `make setup`.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Python launcher 'py' not found. Install Python 3.11+ from python.org (tick 'Add to PATH')." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm not found. Install Node.js 18+ from nodejs.org." }

py -3 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\pip install -e .
Push-Location web
npm install
npm run build
Pop-Location
New-Item -ItemType Directory -Force -Path data | Out-Null

Write-Host ""
Write-Host "Setup complete. Next:"
Write-Host "  tar -xf <path>\cancer-targets-processed-<date>.tar -C data\   # or run the pipeline: ct download / build / score"
Write-Host "  .\.venv\Scripts\ct db"
Write-Host "  .\.venv\Scripts\ct serve      # then open http://localhost:8000"
