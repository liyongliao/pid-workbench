#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONUTF8=1
exec python3 -X utf8 cad-workbench/bootstrap.py
