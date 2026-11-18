#!/usr/bin/env bash
# Rebuild net.json from fresh data. Takes ~10 minutes; needs Python 3.10+.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
python3 fetch_data.py
python3 1_crosscheck.py
python3 2_network.py
python3 3_connect.py
python3 4_export.py
echo "net.json rebuilt. Commit and push it to update the site."
