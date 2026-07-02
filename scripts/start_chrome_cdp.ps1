[CmdletBinding()]
param([ValidateRange(1024, 65535)][int]$Port = 9223)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$profile = Join-Path $root "data\chrome-cdp-profile"
$candidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) { throw "Google Chrome was not found." }

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Host "Chrome CDP is already listening at http://127.0.0.1:$Port"
    return
}

New-Item -ItemType Directory -Path $profile -Force | Out-Null
$arguments = @(
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=$Port",
    "--user-data-dir=$profile",
    "--no-first-run",
    "https://www.xiaohongshu.com/explore"
)
Start-Process -FilePath $chrome -ArgumentList $arguments
Write-Host "Chrome started. Sign in once, then connect MemFlow to http://127.0.0.1:$Port"
