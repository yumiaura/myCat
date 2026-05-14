#!/usr/bin/env bash
# start.sh — launch mycat on the host.
#
# - Creates .venv if missing (--system-site-packages, required for the host's
#   Qt platform plugins on Linux).
# - Installs the package in editable mode the first time.
# - Points the shop at http://127.0.0.1:18000 if a local mycat-server is up.
# - Forwards all extra args to `python -m mycat`.
#
# Usage:
#   ./start.sh                    # run with auto-detected server
#   ./start.sh --openai           # pass-through CLI args
#   MYCAT_SHOP_URL=... ./start.sh # explicit shop URL
#   PYTHON=python3.12 ./start.sh  # pick a different interpreter

set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
PYTHON="${PYTHON:-python3}"

# 1. Virtualenv
if [[ ! -d "$VENV" ]]; then
    echo "[start] creating $VENV (--system-site-packages for Qt plugins)"
    "$PYTHON" -m venv --system-site-packages "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# 2. Editable install if package not importable
if ! python -c "import mycat" 2>/dev/null; then
    echo "[start] installing mycat in editable mode"
    pip install -q --upgrade pip
    pip install -q -e .
fi

# 3. Shop URL — env override > local probe > leave unset (client falls back to default)
if [[ -z "${MYCAT_SHOP_URL:-}" ]]; then
    if command -v curl >/dev/null 2>&1 \
       && curl -fsS --max-time 1 http://127.0.0.1:18000/api/v1/healthz >/dev/null 2>&1; then
        export MYCAT_SHOP_URL="http://127.0.0.1:18000"
        echo "[start] local server reachable → MYCAT_SHOP_URL=$MYCAT_SHOP_URL"
    else
        echo "[start] local mycat-server not reachable on :18000 (shop will use offline cache or default URL)"
    fi
else
    echo "[start] using MYCAT_SHOP_URL=$MYCAT_SHOP_URL (from environment)"
fi

# 4. Go
exec python -m mycat "$@"
