#!/usr/bin/env bash
# Refresh the BytePlus documentation indexes (llms.txt, llms-full.txt, docs/).
#
# Usage:
#   ./refresh.sh                incremental refresh, reusing unchanged bodies
#   ./refresh.sh --full         ignore caches and re-extract every document
set -euo pipefail

cd "$(dirname "$0")"

INCREMENTAL_ARGS=(--incremental-from llms-full.txt --max-age 2592000 --per-library)
if [[ "${1:-}" == "--full" ]]; then
  INCREMENTAL_ARGS=(--refresh --per-library)
elif [[ -n "${1:-}" ]]; then
  echo "usage: refresh.sh [--full]" >&2
  exit 2
fi

echo "==> Discovering and extracting documentation"
python3 generate.py "${INCREMENTAL_ARGS[@]}"

echo "==> Validating outputs"
python3 generate.py --validate-only

echo "==> Syncing standalone skill index"
cp llms.txt .agents/skills/byteplus-docs/llms.txt

if [[ -n "$(git status --porcelain -- llms.txt llms-full.txt docs .agents/skills/byteplus-docs/llms.txt)" ]]; then
  echo "==> Indexes changed; review and commit the updates"
  git status --short -- llms.txt llms-full.txt docs .agents/skills/byteplus-docs/llms.txt
else
  echo "==> No documentation changes detected"
fi
