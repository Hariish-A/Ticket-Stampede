#!/usr/bin/env bash
# M6 demo: the datastore goes slow for 10 s in the middle of the sale.
#
# seller1 talks to Postgres through toxiproxy. The buyer itself adds a latency
# toxic at t=5 s and removes it at t=15 s (on its own clock, so the report's
# timeline and the fault line up). Every answer from Postgres is delayed by
# 3 s -- longer than the seller's 2 s query timeout -- so during the stall
# purchases COMMIT while the seller gives up and answers "unknown": exactly how
# orphaned tickets are born. Buyers retry unclear answers with the same
# request_id (up to 6 times, exponential backoff + jitter).
#
# "Mid-sale" needs a sale still selling at t=5 s: with 100 tickets the sale is
# over in ~0.1 s and a stall would only ever hit sold-out answers. So this uses
# a 15,000-ticket sale (sells ~1,000/s for ~15 s).
#
# Variants (VARIANTS="baseline failfast budget both closed"):
#   baseline -- open-loop client, no protection. First finding: the 10 s stall
#               becomes a ~2 minute outage (retry storm keeps the seller overloaded).
#   failfast -- seller sheds /buy beyond MAX_INFLIGHT=64 in flight with an
#               immediate 503, instead of letting requests queue 1 s for a connection.
#   budget   -- client caps retries at 200/s in total (delays them, never drops).
#   both     -- failfast + budget.
#   closed   -- closed-loop client (4 in flight, ~ the same 1,000 req/s) against
#               the same stall, no protection: the C4 comparison.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

VARIANTS=${VARIANTS:-"baseline failfast budget both closed"}
COMMON=(--tickets 15000 --requests 40000 --burst 1000 --rate 1000
        --stall-at 5 --stall-for 10 --stall-latency-ms 3000 --retry-unknown 6)

docker compose build -q seller1 buyer
runs=()
for v in $VARIANTS; do
  inflight=0; extra=()
  case $v in
    baseline) ;;
    failfast) inflight=64 ;;
    budget)   extra=(--retry-rate 200) ;;
    both)     inflight=64; extra=(--retry-rate 200) ;;
    closed)   extra=(--concurrency 4) ;;
    *) echo "unknown variant $v" >&2; exit 2 ;;
  esac
  DB_HOST=toxiproxy DB_PORT=5433 ALLOCATOR=skiplocked MAX_INFLIGHT=$inflight \
    docker compose up -d --wait toxiproxy seller1 2>&1 | grep -v "^ Container" || true
  echo ">>> $v (MAX_INFLIGHT=$inflight ${extra[*]:-})"
  docker compose run --rm --no-deps buyer run --target http://seller1:8000 --expect-allocator skiplocked \
    --scenario "slowdb-$v" "${COMMON[@]}" "${extra[@]}" "$@" \
    | grep -E "^\| (I[1-4]|A3) |Fault injected|buyers \(user" || true
  runs+=("$(ls -td results/*-slowdb-"$v" | head -1)")
done

# Put seller1 back on the direct connection, unprotected, for the other scenarios.
ALLOCATOR=skiplocked docker compose up -d --wait seller1 2>&1 | grep -v "^ Container" || true

summary="results/$(date -u +%Y%m%dT%H%M%SZ)-slowdb-summary.md"
docker compose run --rm --no-deps buyer compare "${runs[@]}" --timeline \
  --title "M6: Postgres +3 s per answer for 10 s mid-sale (15,000-ticket sale)" --write "$summary"
echo "summary: $summary"
