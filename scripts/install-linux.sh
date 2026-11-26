#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
command -v python3 >/dev/null || { echo '请先安装 Python 3。'; exit 1; }
exec python3 scripts/install_linux.py "$@"
