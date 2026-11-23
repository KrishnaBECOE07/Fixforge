$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment' }
}
& $taskPython -c 'import fastapi, uvicorn'
if ($LASTEXITCODE -ne 0) {
    & $taskPython -m pip install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'web\dist\index.html'))) {
    Push-Location (Join-Path $PSScriptRoot 'web')
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
Write-Host 'FixForge is starting at http://127.0.0.1:8000. Press Ctrl+C to stop.' -ForegroundColor Green
& $taskPython -m fixforge
