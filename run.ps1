Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = $PSScriptRoot
python -m uvicorn BACKEND.app:app --host 127.0.0.1 --port 8000 --reload
