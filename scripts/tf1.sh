#!/usr/bin/env bash
# M8 demo (TF1): three seller instances behind nginx, no application-level lock
# between them -- they share nothing but Postgres. Reruns the key scenarios
# through the load balancer (~25 min in total):
#   1. C1        naive vs skiplocked (duplicates and twins now land on different instances)
#   2. sweep     rate sweep, to compare 1 instance (M5) with 3
#   3. killdb    SIGKILL Postgres mid-sale (one normal run + the sync-off control)
#   4. slowdb    +3 s Postgres answers for 10 s (baseline and client-budget+fail-fast)
# Each step can also be run alone with TOPOLOGY=tf1 ./scripts/<step>.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export TOPOLOGY=tf1

./scripts/c1.sh
PROCESSES=8 RATES="1000 2000 3000 4000 5000 6000" ./scripts/sweep.sh
RUNS="1 off" ./scripts/killdb.sh
VARIANTS="baseline both" ./scripts/slowdb.sh
