#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== [1/2] Node.js API & Board Verification (test.js) ==="
node test.js

echo "=== [2/2] Python Space Board & Search Verification (space/test_board.py) ==="
PYTHONPATH=space python3 space/test_board.py

echo "SNOWGATE-FORUM VERIFICATION PASSED (EXIT 0)"
