#!/bin/sh
# Writes the receipts of <dir> into the newest catalog and pushes. Several workflows write this file: on any collision
# the work starts over from the newest catalog, so one run never loses another's checksums.
# Usage: publish_catalog.sh <receipts_dir> <commit message>
set -u
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
i=0
while [ "$i" -lt 8 ]; do
  i=$((i + 1))
  git fetch -q origin main && git reset -q --hard origin/main || { sleep $((i * 10)); continue; }
  python scripts/update_catalog.py "$1" || exit 1
  git add catalog.json
  git diff --cached --quiet && exit 0
  git commit -q -m "$2"
  git push -q origin HEAD:main && exit 0
  sleep $((i * 15))
done
echo "Catalog not published after $i attempts" >&2
exit 1
