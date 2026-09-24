#!/usr/bin/env bash
# M3 demo (A4 / TF4): how fast can the *client* go?
# The buyer fires at nginx returning canned responses (no seller, no database),
# with 1, 2, 4 and 8 worker processes. Container CPU is sampled alongside, so we
# can see whether the client or nginx saturated first -- if nginx did, the number
# is nginx's ceiling, not the client's, and we say so.
#   ./scripts/calibrate.sh [extra calibrate args, e.g. --rate 80000 --duration 5]
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

docker compose build -q buyer
docker compose up -d lb

stats_file="results/$(date -u +%Y%m%dT%H%M%SZ)-calibrate-container-cpu.txt"
mkdir -p results
( while true; do
    docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}' | sed "s/^/$(date -u +%H:%M:%S) /" >> "$stats_file"
  done ) &
sampler=$!
trap 'kill $sampler 2>/dev/null || true' EXIT

docker compose run --rm --no-deps buyer calibrate --target http://lb:8081 "$@"

kill $sampler 2>/dev/null || true
echo
echo "Peak container CPU during calibration (100% = one core):"
awk '{gsub("%","",$3); if ($3+0 > max[$2]) max[$2]=$3+0} END {for (c in max) printf "  %-45s %6.1f%%\n", c, max[c]}' "$stats_file" | sort
echo "(samples: $stats_file)"
