[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 9223,
    [ValidateRange(5, 120)][int]$StartupTimeoutSec = 30,
    [ValidateRange(5, 120)][int]$CookieProbeTimeoutSec = 20,
    [switch]$RequireXhsLogin,
    [switch]$SkipCookieProbe
)

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

function Get-CdpVersion {
    param([int]$CheckPort)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$CheckPort/json/version" -TimeoutSec 3
        if ($response.StatusCode -ne 200) { return $null }
        $payload = $response.Content | ConvertFrom-Json
        if (-not $payload.webSocketDebuggerUrl) { return $null }
        return $payload
    }
    catch {
        return $null
    }
}

function Test-CdpEndpoint {
    param([int]$CheckPort)
    return [bool](Get-CdpVersion -CheckPort $CheckPort)
}

function Get-CdpTargets {
    param([int]$CheckPort)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$CheckPort/json/list" -TimeoutSec 3
        if ($response.StatusCode -ne 200) { return @() }
        $targets = $response.Content | ConvertFrom-Json
        if ($null -eq $targets) { return @() }
        return @($targets)
    }
    catch {
        return @()
    }
}

function Open-XhsTarget {
    param([int]$CheckPort)
    $encoded = [uri]::EscapeDataString("https://www.xiaohongshu.com/explore")
    try {
        Invoke-WebRequest -UseBasicParsing -Method Put -Uri "http://127.0.0.1:$CheckPort/json/new?$encoded" -TimeoutSec 5 | Out-Null
    }
    catch {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$CheckPort/json/new?$encoded" -TimeoutSec 5 | Out-Null
        }
        catch {
            throw "Chrome CDP is ready, but Xiaohongshu page target could not be opened: $($_.Exception.Message)"
        }
    }
}

function Get-XhsTarget {
    param([int]$CheckPort)
    $targets = Get-CdpTargets -CheckPort $CheckPort
    return $targets |
        Where-Object { $_.type -eq "page" -and $_.webSocketDebuggerUrl -and $_.url -match "xiaohongshu\.com" } |
        Select-Object -First 1
}

function Invoke-CdpCommand {
    param(
        [string]$WebSocketUrl,
        [string]$Method,
        [hashtable]$Params = @{},
        [int]$Id = 1,
        [int]$TimeoutSec = 10
    )

    $ws = [System.Net.WebSockets.ClientWebSocket]::new()
    $cts = [System.Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds($TimeoutSec))
    try {
        $ws.ConnectAsync([uri]$WebSocketUrl, $cts.Token).GetAwaiter().GetResult()
        $message = @{ id = $Id; method = $Method; params = $Params } | ConvertTo-Json -Compress -Depth 8
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($message)
        $ws.SendAsync([ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cts.Token).GetAwaiter().GetResult()

        $buffer = New-Object byte[] 16384
        while (-not $cts.IsCancellationRequested) {
            $builder = [System.Text.StringBuilder]::new()
            do {
                $result = $ws.ReceiveAsync([ArraySegment[byte]]::new($buffer), $cts.Token).GetAwaiter().GetResult()
                if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
                    throw "Chrome closed the DevTools WebSocket while reading cookie state."
                }
                [void]$builder.Append([System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count))
            } while (-not $result.EndOfMessage)

            $payload = $builder.ToString() | ConvertFrom-Json
            if ($payload.id -eq $Id) {
                return $payload
            }
        }
    }
    finally {
        if ($ws.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
            $closeCts = [System.Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds(2))
            try {
                $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $closeCts.Token).GetAwaiter().GetResult()
            }
            catch {}
            finally {
                $closeCts.Dispose()
            }
        }
        $cts.Dispose()
        $ws.Dispose()
    }

    throw "Chrome did not return a DevTools response for $Method within $TimeoutSec seconds."
}

function Test-XhsCookieState {
    param(
        [int]$CheckPort,
        [int]$TimeoutSec,
        [bool]$RequireLogin
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $target = $null
    do {
        $target = Get-XhsTarget -CheckPort $CheckPort
        if ($target) { break }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    if (-not $target) {
        Open-XhsTarget -CheckPort $CheckPort
        do {
            Start-Sleep -Milliseconds 500
            $target = Get-XhsTarget -CheckPort $CheckPort
            if ($target) { break }
        } while ((Get-Date) -lt $deadline)
    }

    if (-not $target) {
        throw "Chrome CDP is ready, but no Xiaohongshu page target appeared within $TimeoutSec seconds."
    }

    Invoke-CdpCommand -WebSocketUrl $target.webSocketDebuggerUrl -Method "Network.enable" -Id 1 -TimeoutSec 5 | Out-Null
    $result = Invoke-CdpCommand -WebSocketUrl $target.webSocketDebuggerUrl -Method "Network.getCookies" -Params @{ urls = @("https://www.xiaohongshu.com") } -Id 2 -TimeoutSec 10
    $cookies = @($result.result.cookies)
    $names = @($cookies | ForEach-Object { $_.name })
    $loginCookieNames = @($names | Where-Object { $_ -in @("web_session", "a1") })

    Write-Host "Xiaohongshu cookie state is readable via Chrome CDP. Cookie count: $($cookies.Count)."
    if ($loginCookieNames.Count -gt 0) {
        Write-Host "Xiaohongshu login cookies detected: $($loginCookieNames -join ', ')."
        return
    }

    $message = "Xiaohongshu cookies are readable, but login cookies were not detected. Sign in to Xiaohongshu in this Chrome profile, then run this script again."
    if ($RequireLogin) {
        throw $message
    }
    Write-Warning $message
}

if (Test-CdpEndpoint -CheckPort $Port) {
    Write-Host "Chrome CDP is ready at http://127.0.0.1:$Port"
    if (-not $SkipCookieProbe) {
        Test-XhsCookieState -CheckPort $Port -TimeoutSec $CookieProbeTimeoutSec -RequireLogin ([bool]$RequireXhsLogin)
    }
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

$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
do {
    Start-Sleep -Milliseconds 500
    if (Test-CdpEndpoint -CheckPort $Port) {
        Write-Host "Chrome CDP is ready at http://127.0.0.1:$Port"
        if (-not $SkipCookieProbe) {
            Test-XhsCookieState -CheckPort $Port -TimeoutSec $CookieProbeTimeoutSec -RequireLogin ([bool]$RequireXhsLogin)
        }
        Write-Host "Sign in to Xiaohongshu in this Chrome profile if prompted."
        return
    }
} while ((Get-Date) -lt $deadline)

throw "Chrome was launched but CDP did not become available at http://127.0.0.1:$Port/json/version within $StartupTimeoutSec seconds. Try running this script from an elevated PowerShell session."
