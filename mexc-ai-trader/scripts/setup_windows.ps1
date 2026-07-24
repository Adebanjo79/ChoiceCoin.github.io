# MEXC AI Trading Assistant - PowerShell setup (Windows)
# Run: Set-ExecutionPolicy -Scope Process Bypass; .\scripts\setup_windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> Creating virtual environment (.venv)" -ForegroundColor Cyan
python -m venv .venv
& .\.venv\Scripts\Activate.ps1

Write-Host "==> Installing dependencies" -ForegroundColor Cyan
python -m pip install --upgrade pip
pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "==> Created .env - edit TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID" -ForegroundColor Yellow
}
else {
    Write-Host "==> .env already exists - leaving it unchanged" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Setup complete. (MEXC SPOT signals)" -ForegroundColor Green
Write-Host "Next:"
Write-Host "  1. Edit .env in VS Code (ACCOUNT_BALANCE_USDT=50, TARGET_UPSIDE_PCT=50)"
Write-Host "  2. Test one pair:  python main.py --symbol BTCUSDT"
Write-Host "  3. One full scan:  python main.py --once"
Write-Host "  4. 24/7 local:     python main.py"
Write-Host "  5. For always-on offline: deploy to a VPS and use PuTTY (see README)"
