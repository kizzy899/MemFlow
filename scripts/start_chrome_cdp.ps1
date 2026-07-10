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

function Test-CdpEndpoint {
    param([int]$CheckPort)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$CheckPort/json/version" -TimeoutSec 3
        if ($response.StatusCode -ne 200) { return $false }
        $payload = $response.Content | ConvertFrom-Json
        return [bool]$payload.webSocketDebuggerUrl
    }
    catch {
        return $false
    }
}

if (Test-CdpEndpoint -CheckPort $Port) {
    Write-Host "Chrome CDP is ready at http://127.0.0.1:$Port"
    return
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    throw "Port $Port is listening but http://127.0.0.1:$Port/json/version is not a Chrome CDP endpoint. Stop the process using this port or choose another port."
}

New-Item -ItemType Directory -Path $profile -Force | Out-Null
$arguments = @(
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=$Port",
    "--user-data-dir=$profile",
    "--no-first-run",
    "--new-window",
    "https://www.xiaohongshu.com/explore"
)
Start-Process -FilePath $chrome -ArgumentList $arguments | Out-Null

$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 500
    if (Test-CdpEndpoint -CheckPort $Port) {
        Write-Host "Chrome CDP is ready at http://127.0.0.1:$Port"
        Write-Host "Sign in to Xiaohongshu in this Chrome profile if prompted."
        return
    }
} while ((Get-Date) -lt $deadline)

throw "Chrome was launched but CDP did not become available at http://127.0.0.1:$Port/json/version within 20 seconds. Try running this script from an elevated PowerShell session."