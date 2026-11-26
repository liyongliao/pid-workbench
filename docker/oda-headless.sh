#!/bin/sh
set -eu
export QT_QPA_PLATFORM=xcb
cd /engine
exec xvfb-run -a -s "-screen 0 1024x768x24 -nolisten tcp" ./ODAFileConverter "$@"
