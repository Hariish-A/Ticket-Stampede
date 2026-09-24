#!/usr/bin/env bash
# M5 demo: how much load before latency degrades, and where is the bottleneck?
# Steps a steady open-loop rate up against one seller and, during every step,
# samples container CPU (docker stats) and Postgres wait events
# (pg_stat_activity). Writes results/<ts>-sweep/summary.md.
#   RATES="250 500 1000 1500 2000 3000" DURATION=15 ./scripts/sweep.sh
#   TOPOLOGY=tf1 PROCESSES=8 RATES="1000 2000 3000 4000 5000 6000" ./scripts/sweep.sh   # 3 sellers behind nginx (M8)
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
source scripts/lib.sh
PROCESSES=${PROCESSES:-4}
suffix=""; [ "$TOPOLOGY" = tf1 ] && suffix="-tf1"

RATES=${RATES:-"250 500 1000 1500 2000 2500 3000 4000"}
DURATION=${DURATION:-15}
ALLOC=${ALLOCATOR:-skiplocked}
sweep_dir="results/$(date -u +%Y%m%dT%H%M%SZ)-sweep$suffix"
mkdir -p "$sweep_dir"

docker compose build -q $SELLERS buyer
start_sellers ALLOCATOR="$ALLOC"

PGWAIT_SQL="select state, coalesce(wait_event_type,''), coalesce(wait_event,'') from pg_stat_activity
            where datname = 'tickets' and backend_type = 'client backend' and pid <> pg_backend_pid()"

# Warm-up, discarded: a freshly (re)created seller has a cold pool, cold
# prepared-statement caches and a cold interpreter. Without this, the first
# step's p99 measured the cold start (185 ms at 250 req/s), not the load.
echo ">>> warm-up (not recorded)"
docker compose run --rm --no-deps buyer run --target "$TARGET" --processes "$PROCESSES" --scenario sweep-warmup \
  --requests 3000 --burst 0 --rate 500 --dup-concurrent 0 --dup-sequential 0 --audit-interval 0 \
  --out /tmp/warmup >/dev/null 2>&1 || true

runs=()
for rate in $RATES; do
  n=$(( rate * DURATION ))
  ( while true; do docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}' \
      | sed "s/^/$(date -u +%H:%M:%S) /" >> "$sweep_dir/cpu-$rate.txt"; done ) &
  cpu_pid=$!
  ( while true; do docker compose exec -T postgres psql -U tickets -d tickets -At -F'|' -c "$PGWAIT_SQL" \
      >> "$sweep_dir/pgwait-$rate.txt" 2>/dev/null; echo "--" >> "$sweep_dir/pgwait-$rate.txt"; sleep 0.2; done ) &
  pg_pid=$!

  echo ">>> $rate req/s for ${DURATION}s ($n requests)"
  # Steady rate, no opening burst: we want the sustainable rate, not the burst.
  # Auditor off: it would add its own /status load to the thing being measured.
  docker compose run --rm --no-deps buyer run --target "$TARGET" --expect-allocator "$ALLOC" \
    --processes "$PROCESSES" --scenario "sweep$suffix-$rate" --requests "$n" --burst 0 --rate "$rate" \
    --dup-concurrent 0 --dup-sequential 0 --audit-interval 0 "$@" \
    | grep -E "req/s handled|^\| latency" || true

  kill $cpu_pid $pg_pid 2>/dev/null || true
  wait $cpu_pid $pg_pid 2>/dev/null || true
  runs+=("$(ls -td results/*-sweep"$suffix"-"$rate" | head -1)")
done

printf '%s\n' "${runs[@]}" > "$sweep_dir/runs.txt"
docker compose run --rm --no-deps --entrypoint python buyer -m buyer.sweep_report "$sweep_dir" "${runs[@]}"
echo "summary: $sweep_dir/summary.md"
