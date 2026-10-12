#!/bin/sh
# Usage: tools/stems/run.sh [input_dir] [output_dir] [--fast|--max-quality] [--only NAME] [--redo]
cd "$(dirname "$0")/../.." || exit 1
exec tools/stems/.venv/bin/python tools/stems/studio.py "$@"
