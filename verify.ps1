$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    Write-Host "=== [1/2] Node.js API & Board Verification (test.js) ==="
    node test.js
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "=== [2/2] Python Space Board & Search Verification (space/test_board.py) ==="
    $env:PYTHONPATH = Join-Path $PSScriptRoot "space"
    python space/test_board.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "SNOWGATE-FORUM VERIFICATION PASSED (EXIT 0)"
} finally {
    Pop-Location
}
