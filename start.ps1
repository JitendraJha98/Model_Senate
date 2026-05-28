$ErrorActionPreference = "Stop"

Write-Host "Starting Model_Senate backend on http://127.0.0.1:8001"
Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoExit", "-Command", "uv run python -m backend.main"

Write-Host "Starting Model_Senate frontend on http://localhost:5173"
Push-Location frontend
npm run dev
Pop-Location
