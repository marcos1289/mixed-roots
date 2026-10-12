#!/bin/sh
# One improvement cycle: learn from the band's picks, generate a new batch, publish it.
#   tools/compose/cycle.sh [number of variants, default 4]
set -e
cd "$(dirname "$0")/../.."
PY=tools/stems/.venv/bin/python
$PY tools/compose/learn.py
$PY tools/compose/evolve.py --n "${1:-4}"
$PY tools/stems/publish_private.py
git add tools/compose/learned.json tools/compose/songs/batches docs/studio-*
git commit -q -m "Studio: new song batch from the band's ratings" && git push -q origin main
echo "Published. Rate the new hooks on the studio page's Compare tab."
