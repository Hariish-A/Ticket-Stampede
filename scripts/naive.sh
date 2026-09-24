#!/usr/bin/env bash
# M1 demo: the naive seller under a stampede. Expected: the buyer reports FAILs.
#   ./scripts/naive.sh [extra buyer args...]
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: don't rewrite container paths

ALLOCATOR=naive docker compose up -d --build --wait seller1
docker compose build buyer >/dev/null

set +e
docker compose run --rm --no-deps buyer run --target http://seller1:8000 --expect-allocator naive --scenario naive "$@"
code=$?
set -e

if [ "$code" -eq 1 ]; then
  echo ">>> naive seller caught violating invariants (expected)."
  exit 0
elif [ "$code" -eq 0 ]; then
  echo ">>> naive seller passed every invariant -- the attack did not expose the race." >&2
  exit 1
fi
exit "$code"
