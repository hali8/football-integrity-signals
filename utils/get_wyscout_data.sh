#!/usr/bin/env bash
#
# Thin convenience wrapper around the packaged downloader.
#
# The real implementation is src/fis/data/wyscout.py -- it pins the upstream
# commit, needs no git, and resolves the destination the same way every other
# entry point does (FIS_DATA_DIR > project root > user cache).
#
# Equivalent to:  fis-fetch-wyscout    (once the package is installed)
#
# Any arguments are passed straight through, e.g.:
#   ./utils/get_wyscout_data.sh --force
#   ./utils/get_wyscout_data.sh --dest /scratch/wyscout
#
set -euo pipefail

if command -v fis-fetch-wyscout >/dev/null 2>&1; then
  exec fis-fetch-wyscout "$@"
fi

# Not installed: run from the source tree.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m fis.data.wyscout "$@"
