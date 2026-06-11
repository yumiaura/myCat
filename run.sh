#!/usr/bin/env bash
# Launch mycat on Linux. Passes through any flags, e.g.:
#   ./run.sh                # default
#   ./run.sh --openai       # OpenAI chat
#   ./run.sh --ollama       # Ollama chat
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m mycat "$@"
