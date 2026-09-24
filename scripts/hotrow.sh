#!/usr/bin/env bash
# M5 experiment: is the counter strategy's ~250 claims/s ceiling the disk's
# commit flush? Runs the large sale with counter and skiplocked, each with
# synchronous_commit on (the real setting) and off (commits acknowledged
# before the WAL flush -- NOT durable, an experiment only), then restores it.
# If counter speeds up a lot with the flush removed while skiplocked barely
# changes, the hot row serialises commit flushes (no group commit possible
# while the row lock is held until the flush completes).
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

psql() { docker compose exec -T postgres psql -U tickets -d tickets -At "$@"; }
# ALTER DATABASE, not ALTER SYSTEM: the compose file passes synchronous_commit on
# postgres' command line, which outranks postgresql.auto.conf. The first version
# of this script used ALTER SYSTEM, silently ran "off" as "on", and was caught
# only because it printed SHOW synchronous_commit. A database-level setting
# outranks the command line but applies to *new* sessions, so seller1 restarts.
restore() { psql -c "ALTER DATABASE tickets RESET synchronous_commit" >/dev/null; }
trap restore EXIT

docker compose build -q seller1 buyer
runs=()
for alloc in counter skiplocked; do
  ALLOCATOR="$alloc" docker compose up -d --wait seller1 2>&1 | grep -v "^ Container" || true
  for mode in on off; do
    psql -c "ALTER DATABASE tickets SET synchronous_commit = $mode" >/dev/null
    ALLOCATOR="$alloc" docker compose restart seller1 >/dev/null 2>&1
    ALLOCATOR="$alloc" docker compose up -d --wait seller1 2>&1 | grep -v "^ Container" || true
    actual=$(psql -c 'SHOW synchronous_commit')
    echo ">>> $alloc, synchronous_commit=$actual (as a new session sees it)"
    [ "$actual" = "$mode" ] || { echo "setting did not apply; aborting" >&2; exit 1; }
    docker compose run --rm --no-deps buyer run --target http://seller1:8000 --expect-allocator "$alloc" \
      --scenario "hotrow-$alloc-sync-$mode" --tickets 5000 --requests 20000 --burst 2000 --rate 1000 \
      --audit-interval 0 | grep -E "req/s handled|First sold-out" || true
    runs+=("$(ls -td results/*-hotrow-"$alloc"-sync-"$mode" | head -1)")
  done
done
restore
echo ">>> restored: synchronous_commit=$(psql -c 'SHOW synchronous_commit')"
summary="results/$(date -u +%Y%m%dT%H%M%SZ)-hotrow-summary.md"
docker compose run --rm --no-deps buyer compare "${runs[@]}" \
  --title "Hot row: commit flush on vs off (large sale, 5,000 tickets)" --write "$summary"
echo "summary: $summary"
