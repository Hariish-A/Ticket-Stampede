#!/usr/bin/env bash
# All automated tests, inside containers (no local Python setup needed):
#   1. buyer unit tests  -- the verifier catches every planted violation
#   2. seller integration tests -- each race against the real Postgres
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

echo "== buyer unit tests"
docker compose build -q buyer
docker compose run --rm --no-deps --entrypoint python buyer -m pytest -q tests

echo "== seller integration tests (against Postgres)"
docker compose build -q seller-tests
docker compose up -d --wait postgres
docker compose run --rm seller-tests
