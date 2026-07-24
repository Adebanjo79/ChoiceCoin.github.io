# Set Telegram values into .env from PowerShell (no Notepad needed)
# Usage:
#   .\scripts\set_telegram.ps1
# Or with args:
#   .\scripts\set_telegram.ps1 -BotToken "123:AAH..." -ChatId "123456789"

param(
    [string]$BotToken = "",
    [string]$ChatId = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$envFile = Join-Path $Root ".env"
$example = Join-Path $Root ".env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $example) {
        Copy-Item $example $envFile
        Write-Host "Created .env from .env.example" -ForegroundColor Yellow
    }
    else {
        New-Item -Path $envFile -ItemType File | Out-Null
        Write-Host "Created empty .env" -ForegroundColor Yellow
    }
}

if (-not $BotToken) {
    $BotToken = Read-Host "Paste TELEGRAM_BOT_TOKEN (from @BotFather)"
}
if (-not $ChatId) {
    $ChatId = Read-Host "Paste TELEGRAM_CHAT_ID (from @userinfobot)"
}

$BotToken = $BotToken.Trim().Trim('"').Trim("'")
$ChatId = $ChatId.Trim().Trim('"').Trim("'")

if (-not $BotToken -or $BotToken -notmatch ":") {
    Write-Host "ERROR: Bot token looks invalid. It must contain a colon (:)" -ForegroundColor Red
    exit 1
}
if (-not $ChatId) {
    Write-Host "ERROR: Chat ID is empty" -ForegroundColor Red
    exit 1
}

# Read existing .env and upsert the two keys
$lines = @()
if (Test-Path $envFile) {
    $lines = Get-Content $envFile -ErrorAction SilentlyContinue
}

$out = New-Object System.Collections.Generic.List[string]
$seenToken = $false
$seenChat = $false

foreach ($line in $lines) {
    if ($line -match '^\s*TELEGRAM_BOT_TOKEN\s*=') {
        $out.Add("TELEGRAM_BOT_TOKEN=$BotToken")
        $seenToken = $true
    }
    elseif ($line -match '^\s*TELEGRAM_CHAT_ID\s*=') {
        $out.Add("TELEGRAM_CHAT_ID=$ChatId")
        $seenChat = $true
    }
    else {
        $out.Add($line)
    }
}

if (-not $seenToken) { $out.Add("TELEGRAM_BOT_TOKEN=$BotToken") }
if (-not $seenChat) { $out.Add("TELEGRAM_CHAT_ID=$ChatId") }

# Ensure useful defaults exist
$joined = ($out -join "`n")
if ($joined -notmatch 'ACCOUNT_BALANCE_USDT=') { $out.Add("ACCOUNT_BALANCE_USDT=50") }
if ($joined -notmatch 'TARGET_UPSIDE_PCT=') { $out.Add("TARGET_UPSIDE_PCT=50") }
if ($joined -notmatch 'MIN_CONFIDENCE=') { $out.Add("MIN_CONFIDENCE=70") }
if ($joined -notmatch 'QUALITY_FILTERS=') { $out.Add("QUALITY_FILTERS=true") }
if ($joined -notmatch 'TELEGRAM_STATUS=') { $out.Add("TELEGRAM_STATUS=false") }

$out | Set-Content -Path $envFile -Encoding UTF8

Write-Host ""
Write-Host "Saved to .env" -ForegroundColor Green
Write-Host ("Token preview: {0}...{1}" -f $BotToken.Substring(0, [Math]::Min(6, $BotToken.Length)), $BotToken.Substring([Math]::Max(0, $BotToken.Length - 4)))
Write-Host "Chat ID: $ChatId"
Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python scripts/check_telegram.py"
Write-Host "  # or: python main.py --test-telegram"
