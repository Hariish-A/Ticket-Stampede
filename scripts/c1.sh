#!/usr/bin/env bash
# M2 demo (C1): the identical attack -- same schedule, same seed -- against the
# naive seller and then the safe one. Expected: naive FAILs, skiplocked PASSes.
#   ./scripts/c1.sh [extra buyer args...]
#   TOPOLOGY=tf1 ./scripts/c1.sh     # the same, against 3 sellers behind nginx (M8)
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
source scripts/lib.sh

docker compose build -q $SELLERS buyer
suffix=""; [ "$TOPOLOGY" = tf1 ] && suffix="-tf1"

run() {  # run <allocator>; prints the buyer report, returns the buyer's exit code
  start_sellers ALLOCATOR="$1"
  # --no-deps: without it, `compose run` re-reads the file with ALLOCATOR unset and
  # silently recreates the seller on the default allocator (this happened; see Progress.md).
  # --expect-allocator makes the buyer refuse to attack the wrong seller at all.
  docker compose run --rm --no-deps buyer run --target "$TARGET" \
    --expect-allocator "$1" --scenario "c1-$1$suffix" "${@:2}"
}

set +e
run naive "$@";      naive=$?
run skiplocked "$@"; safe=$?
set -e

echo
echo ">>> naive:      $([ $naive -eq 1 ] && echo 'FAIL (caught, as expected)' || echo "exit $naive -- NOT caught")"
echo ">>> skiplocked: $([ $safe -eq 0 ] && echo 'PASS' || echo "exit $safe -- FAILED")"
[ $naive -eq 1 ] && [ $safe -eq 0 ]
