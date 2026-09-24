#!/usr/bin/env bash
# M7 demo (TF2): kill the datastore in the middle of the sale and bring it back.
#
# The buyer runs a 15,000-ticket sale for 40,000 buyers (the kill must land while
# tickets are still selling; with 100 tickets the sale is over in ~0.1 s). A few
# seconds in, Postgres gets SIGKILL -- no shutdown, no checkpoint, every backend
# and the postmaster die mid-statement. After DOWN seconds it is started again,
# replays its WAL (crash recovery), and the sale continues. Buyers retry unclear
# answers with the same request_id (retry budget 200/s, M6).
#
# Must hold: no oversell, no duplicate ticket number, and no confirmed sale lost
# (a ticket confirmed to a buyer and then missing from /status is a "phantom";
# I4 fails on any). The report also lists every purchase that was in flight at
# the instant of the kill and whether it had committed.
#
# RUNS (default "1 2 3 off"):
#   1 2 3 -- normal runs (synchronous_commit=on), different seeds and kill times
#   off   -- CONTROL: synchronous_commit=off, i.e. commits acknowledged before
#            their WAL is flushed. This one SHOULD lose confirmed sales; if the
#            harness does not catch it, a PASS on the real runs means nothing.
#
# `docker kill` is a process crash, not a power cut: WAL already handed to the
# kernel survives it even unflushed. This demonstrates crash safety of the
# process, not power-loss durability of the disk.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
source scripts/lib.sh   # TOPOLOGY=tf1: the same, against 3 sellers behind nginx (M8)
suffix=""; [ "$TOPOLOGY" = tf1 ] && suffix="-tf1"

RUNS=${RUNS:-"1 2 3 off"}
DOWN=${DOWN:-5}
PG=ticket-stampede-postgres-1

psql() { docker compose exec -T postgres psql -U tickets -d tickets -At "$@"; }
vmnow() {  # wall clock of the Docker VM -- the clock the buyer's timestamps use
  docker compose exec -T seller1 python -c 'import time; print(f"{time.time():.3f}")' | tr -d '\r'
}
set_sync() {  # ALTER DATABASE (see hotrow.sh: the -c flag outranks ALTER SYSTEM); new sessions only
  psql -c "ALTER DATABASE tickets SET synchronous_commit = $1" >/dev/null
  restart_sellers ALLOCATOR=skiplocked
  local actual; actual=$(psql -c 'SHOW synchronous_commit' | tr -d '\r')
  [ "$actual" = "$1" ] || { echo "synchronous_commit=$1 did not apply (got $actual)" >&2; exit 1; }
}
restore() {
  docker compose start postgres >/dev/null 2>&1 || true
  until [ "$(docker inspect -f '{{.State.Health.Status}}' $PG 2>/dev/null)" = healthy ]; do sleep 0.5; done
  psql -c "ALTER DATABASE tickets RESET synchronous_commit" >/dev/null || true
}
trap restore EXIT

docker compose build -q $SELLERS buyer
start_sellers ALLOCATOR=skiplocked

runs=()
for r in $RUNS; do
  sync=on; seed=$r; kill_after=$(( 6 + 2 * ${r//off/2} ))
  [ "$r" = off ] && { sync=off; seed=4; }
  set_sync "$sync"
  label="killdb$suffix-$r"; events="results/.$label-events.json"; rm -f "$events"
  echo ">>> run $r: synchronous_commit=$sync, SIGKILL postgres ~${kill_after}s after launch, down ${DOWN}s"

  docker compose run --rm --no-deps buyer run --target "$TARGET" --expect-allocator skiplocked \
    --scenario "$label" --seed "$seed" --tickets 15000 --requests 40000 --burst 1000 --rate 1000 \
    --retry-unknown 10 --retry-rate 200 --fault-file "$events" "$@" > "results/.$label.out" 2>&1 &
  buyer=$!

  sleep "$kill_after"
  docker compose kill -s SIGKILL postgres >/dev/null 2>&1
  t_fault=$(vmnow)          # just after the kill returned: the kill happened by now
  sleep "$DOWN"
  t_restart=$(vmnow)
  docker compose start postgres >/dev/null 2>&1
  until [ "$(docker inspect -f '{{.State.Health.Status}}' $PG)" = healthy ]; do sleep 0.2; done
  t_recovered=$(vmnow)
  printf '{"kind": "kill", "detail": "SIGKILL postgres, restart after %ss, synchronous_commit=%s", "events": {"fault": %s, "restart": %s, "recovered": %s}}\n' \
    "$DOWN" "$sync" "$t_fault" "$t_restart" "$t_recovered" > "$events"
  docker compose logs postgres --since 30s 2>&1 | grep -E "not properly shut down|redo (starts|done)" | tail -3 || true

  wait $buyer || true
  grep -E "^\| (I[1-4]|A3) |in flight at the instant|^- (answered|unclear)|buyers \(user" "results/.$label.out" || true
  runs+=("$(ls -td results/*-"$label" | head -1)")
  rm -f "$events" "results/.$label.out"
done

restore
summary="results/$(date -u +%Y%m%dT%H%M%SZ)-killdb$suffix-summary.md"
docker compose run --rm --no-deps buyer compare "${runs[@]}" --timeline \
  --title "M7 / TF2: SIGKILL Postgres mid-sale, restart after ${DOWN}s (runs: $RUNS)" --write "$summary"
echo "summary: $summary"
