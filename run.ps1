Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}
& $python -m uvicorn BACKEND.app:app --host 127.0.0.1 --port 8000
