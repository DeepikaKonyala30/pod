$ErrorActionPreference = "Stop"

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "   PodMind - Starting Services (Windows)" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

# 1. Start Redis
Write-Host "[1/4] Starting Redis via Docker..." -ForegroundColor Yellow
docker-compose up -d redis

# 2. Setup Virtual Environment
Write-Host "[2/4] Setting up Python Environment..." -ForegroundColor Yellow
if (-not (Test-Path "venv")) {
    python -m venv venv
}
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Start FastAPI Backend in new window
Write-Host "[3/4] Starting FastAPI Backend (Port 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList '-NoExit', '-Command', '.\venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload'

# 4. Start React Dashboard
Write-Host "[4/4] Starting React Dashboard (Port 5173)..." -ForegroundColor Yellow
cd dashboard
npm install
npm run dev