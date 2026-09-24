#!/usr/bin/env bash
# M5 check of decision D10: does it matter that the buyer runs inside the
# compose network? Same load, same seller, two paths:
#   direct  -- buyer -> seller1:8000 on the compose network
#   hostfwd -- buyer -> host.docker.internal:8001, i.e. out through Docker
#              Desktop's published-port forwarding, as a client on the host would
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

RATE=${RATE:-800}
DURATION=${DURATION:-15}
docker compose build -q seller1 buyer
ALLOCATOR=skiplocked docker compose up -d --wait seller1 2>&1 | grep -v "^ Container" || true

REPS=${REPS:-3}
fire() {  # fire <path> <scenario> [extra args]
  local target=http://seller1:8000
  [ "$1" = hostfwd ] && target="http://host.docker.internal:${SELLER1_PORT:-8001}"
  docker compose run --rm --no-deps buyer run --target "$target" --scenario "$2" \
    --requests $(( RATE * DURATION )) --burst 0 --rate "$RATE" --dup-concurrent 0 --dup-sequential 0 \
    --audit-interval 0 "${@:3}"
}
# The first version ran each path once, direct always first -- right after `up`,
# which can recreate the seller. Direct then carried the cold start (p99 ~280 ms
# vs ~8 ms, twice). Now: a discarded warm-up, then REPS rounds with the order
# alternated, so position in the sequence cannot masquerade as a path effect.
fire direct d10-warmup --out /tmp/warmup >/dev/null 2>&1 || true
runs=()
for rep in $(seq "$REPS"); do
  order="direct hostfwd"; [ $(( rep % 2 )) -eq 0 ] && order="hostfwd direct"
  for path in $order; do
    echo ">>> round $rep: $path"
    fire "$path" "d10-$path" --seed "$rep" | grep -E "req/s handled|^\| latency" || true
    runs+=("$(ls -td results/*-d10-"$path" | head -1)")
  done
done
summary="results/$(date -u +%Y%m%dT%H%M%SZ)-d10-summary.md"
docker compose run --rm --no-deps buyer compare "${runs[@]}" \
  --title "D10: buyer on the compose network vs through the host's published port" --write "$summary"
echo "summary: $summary"
