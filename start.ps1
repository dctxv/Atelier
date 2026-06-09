# Atelier v2 — start script
# Run from c:\Atelier:  .\start.ps1

Set-Location $PSScriptRoot

# Kill anything already on port 8000 so we start clean
$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($conn) {
    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

Write-Host ""
Write-Host "  Atelier v2" -ForegroundColor DarkYellow
Write-Host "  http://127.0.0.1:8000" -ForegroundColor DarkYellow
Write-Host ""

python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
