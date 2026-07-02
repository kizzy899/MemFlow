[CmdletBinding()]
param(
    [string]$BindAddress = "127.0.0.1",

    [ValidateRange(1, 65535)]
    [int]$Port = 8000,

    [switch]$NoReload,

    [switch]$Check
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Virtual environment not found. Run 'python -m venv .venv' and install requirements first."
}

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ".env") -PathType Leaf)) {
    Write-Warning ".env was not found. Copy .env.example to .env and configure it before using external services."
}

Push-Location $projectRoot
try {
    & $python -c "import uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "uvicorn is not installed in .venv. Run '.venv\Scripts\python.exe -m pip install -r requirements.txt'."
    }

    if ($Check) {
        Write-Host "MemFlow startup check passed."
        return
    }

    $uvicornArgs = @(
        "-m", "uvicorn",
        "app.main:app",
        "--host", $BindAddress,
        "--port", $Port.ToString()
    )
    # Auto-reload uses a Windows selector loop that cannot host the
    # persistent Playwright process required by QR login.

    Write-Host "Starting MemFlow at http://${BindAddress}:$Port"
    Write-Host "Knowledge Console: http://${BindAddress}:$Port/console"
    & $python @uvicornArgs
    if ($LASTEXITCODE -ne 0) {
        throw "MemFlow exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
