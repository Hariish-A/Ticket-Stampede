#!/usr/bin/env bash
# M5: where does the seller's CPU go? Puts steady load on seller1, attaches
# py-spy to the running server for 10 s, and summarises the samples by layer
# (HTTP server, framework, DB driver, our code, event loop). Also records the
# disk's fsync rate (pg_test_fsync), which bounds any design that commits on a
# hot row. Writes results/<ts>-profile/.
#   RATE=2000 ./scripts/profile.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

RATE=${RATE:-2000}
DURATION=${DURATION:-25}
SAMPLE_HZ=250
ALLOC=${ALLOCATOR:-skiplocked}
out="results/$(date -u +%Y%m%dT%H%M%SZ)-profile-$ALLOC-$RATE"
mkdir -p "$out"

docker compose build -q seller1 buyer
ALLOCATOR="$ALLOC" docker compose up -d --wait seller1 2>&1 | grep -v "^ Container" || true

docker compose run --rm --no-deps buyer run --target http://seller1:8000 --expect-allocator "$ALLOC" \
  --scenario "profile-$RATE" --requests $(( RATE * DURATION )) --burst 0 --rate "$RATE" \
  --dup-concurrent 0 --dup-sequential 0 --audit-interval 0 > "$out/buyer-report.md" 2>&1 &
buyer=$!

sleep 8  # let the load reach steady state
echo ">>> py-spy: 10 s at ${SAMPLE_HZ} Hz on seller1 under $RATE req/s"
docker compose exec -T seller1 py-spy record --pid 1 --duration 10 --rate $SAMPLE_HZ \
  --format raw --output /tmp/pyspy.txt --nonblocking >/dev/null 2>&1
docker compose cp seller1:/tmp/pyspy.txt "$out/pyspy-raw.txt" >/dev/null 2>&1
wait $buyer || true

echo ">>> pg_test_fsync (how many durable commits/s this disk allows)"
docker compose exec -T postgres pg_test_fsync -s 2 -f /var/lib/postgresql/data/pg_test_fsync.tmp \
  > "$out/pg_test_fsync.txt" 2>&1 || true

docker compose run --rm --no-deps --entrypoint python buyer -m buyer.profile_report \
  "$out/pyspy-raw.txt" "$SAMPLE_HZ" 10 | tee "$out/summary.md"
grep -E "fdatasync|open_datasync|fsync " "$out/pg_test_fsync.txt" | head -6 | tee -a "$out/summary.md"
echo "results: $out"
