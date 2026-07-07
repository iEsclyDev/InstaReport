#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
if [ -f ".venv/bin/python" ]; then
    exec .venv/bin/python main.py "$@"
else
    exec python3 main.py "$@"
fi
