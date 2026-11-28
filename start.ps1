$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$fixforgePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $fixforgePython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment' }
}

& $fixforgePython -c 'import sys; sys.exit(sys.version_info < (3, 11))'
if ($LASTEXITCODE -ne 0) { throw 'FixForge requires Python 3.11 or later. Recreate .venv with a supported Python.' }

$pythonLock = (Get-FileHash -LiteralPath 'requirements.lock').Hash
$pythonStamp = '.venv\fixforge-requirements.sha256'
if (-not (Test-Path -LiteralPath $pythonStamp) -or (Get-Content -LiteralPath $pythonStamp -Raw) -ne $pythonLock) {
    & $fixforgePython -m pip install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    Set-Content -LiteralPath $pythonStamp -Value $pythonLock -NoNewline
}

Push-Location -LiteralPath (Join-Path $PSScriptRoot 'web')
try {
    $nodeLock = (Get-FileHash -LiteralPath 'package-lock.json').Hash
    $nodeStamp = 'node_modules\fixforge-package-lock.sha256'
    if (-not (Test-Path -LiteralPath $nodeStamp) -or (Get-Content -LiteralPath $nodeStamp -Raw) -ne $nodeLock) {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
        Set-Content -LiteralPath $nodeStamp -Value $nodeLock -NoNewline
    }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally {
    Pop-Location
}

Write-Host 'Starting FixForge. Press Ctrl+C to stop.' -ForegroundColor Green
& $fixforgePython -m fixforge
exit $LASTEXITCODE
