#!/usr/bin/env bash
# start.sh — launch mycat on the host.
#
# Usage:
#   ./start.sh                    # run
#   ./start.sh --openai           # pass-through CLI args
#   MYCAT_SHOP_URL=... ./start.sh # explicit shop URL
#   PYTHON=python3.12 ./start.sh  # pick a different interpreter

set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

# X11 display — if the shell didn't inherit one (tmux / fresh ssh / detached
# terminal), find the user's X socket in /tmp/.X11-unix/X<N> and use that.
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    for sock in /tmp/.X11-unix/X*; do
        [[ -S "$sock" ]] || continue
        [[ "$(stat -c %u "$sock" 2>/dev/null)" == "$(id -u)" ]] || continue
        export DISPLAY=":${sock##*/X}"
        echo "[start] auto-detected DISPLAY=$DISPLAY (from $sock)"
        break
    done
    if [[ -z "${DISPLAY:-}" ]]; then
        echo "[start] no X socket found for uid $(id -u) in /tmp/.X11-unix/; GUI will fail"
    fi
fi

# Shop URL — env override > local probe > leave unset (client uses its default)
if [[ -z "${MYCAT_SHOP_URL:-}" ]]; then
    if command -v curl >/dev/null 2>&1 \
       && curl -fsS --max-time 1 http://127.0.0.1:18000/api/v1/healthz >/dev/null 2>&1; then
        export MYCAT_SHOP_URL="http://127.0.0.1:18000"
        echo "[start] local server reachable → MYCAT_SHOP_URL=$MYCAT_SHOP_URL"
    fi
fi

exec "$PYTHON" -m mycat "$@"
