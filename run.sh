#!/usr/bin/env bash
# Launch mycat on Linux/macOS. Passes through any flags, e.g.:
#   ./run.sh                     # default
#   ./run.sh --openai            # OpenAI chat
#   ./run.sh --ollama            # Ollama chat
#   PYTHON=python3.12 ./run.sh   # pick a different interpreter
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

# X11 display (Linux): if the shell didn't inherit one — tmux, a fresh ssh
# session, a detached terminal — pick the first local X socket in
# /tmp/.X11-unix/X<N> and use it. (The socket is usually root-owned, so we
# don't gate on ownership.) macOS draws through Cocoa, so it's skipped there,
# and a Wayland session is left untouched.
if [[ "$(uname)" != "Darwin" && -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    for sock in /tmp/.X11-unix/X*; do
        [[ -S "$sock" ]] || continue
        export DISPLAY=":${sock##*/X}"
        echo "[run] auto-detected DISPLAY=$DISPLAY (from $sock)"
        break
    done
    if [[ -z "${DISPLAY:-}" ]]; then
        echo "[run] no X socket found in /tmp/.X11-unix/; the GUI may fail"
    fi
fi

exec "$PYTHON" -m mycat "$@"
