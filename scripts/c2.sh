#!/usr/bin/env bash
# M4 demo (C2): three correct allocation strategies under the identical load.
#   serializable -- SERIALIZABLE transaction + retry (the textbook answer)
#   counter      -- one shared counter row (every buyer queues on one lock)
#   skiplocked   -- claim the lowest unsold row, skipping rows mid-claim
# Two workloads:
#   brief -- 100 tickets, 50k buyers: the sale is over within the opening burst,
#            so this mostly measures the sold-out path.
#   large -- 5,000 tickets, 20k buyers: contention lasts long enough to measure
#            the claim path itself.
# Writes results/<ts>-c2-summary.md.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

docker compose build -q seller1 buyer

declare -A WORKLOAD=(
  [brief]=""
  [large]="--tickets 5000 --requests 20000 --burst 2000 --rate 1000"
)
runs=()
for w in brief large; do
  for alloc in serializable counter skiplocked; do
    ALLOCATOR="$alloc" docker compose up -d --wait seller1 2>&1 | grep -v "^ Container" || true
    scenario="c2-$w-$alloc"
    # shellcheck disable=SC2086
    docker compose run --rm --no-deps buyer run --target http://seller1:8000 --expect-allocator "$alloc" \
      --scenario "$scenario" ${WORKLOAD[$w]} "$@" | grep -E "^\| (I[1-4]|A3) |req/s|Seller counters" || true
    runs+=("$(ls -td results/*-"$scenario" | head -1)")
  done
done

summary="results/$(date -u +%Y%m%dT%H%M%SZ)-c2-summary.md"
docker compose run --rm --no-deps buyer compare "${runs[@]}" \
  --title "C2: allocation strategies under identical load" --write "$summary"
echo "summary: $summary"
