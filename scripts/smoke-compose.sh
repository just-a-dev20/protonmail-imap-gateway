#!/bin/sh
# This validates an unconfigured engine, not Proton authentication or mail sync.
set -eu
sh scripts/init-secrets.sh
cat > compose.ci.yml <<'YAML'
services:
  gateway:
    image: gateway:ci
    pull_policy: never
YAML
trap 'docker compose -f docker-compose.yml -f compose.ci.yml down -v; rm -f compose.ci.yml' EXIT
docker compose -f docker-compose.yml -f compose.ci.yml config --quiet
# Bridge's batch-capable CLI exports its generated certificate without login.
printf 'cert export\n/data/bridge-cert\nexit\n' | docker compose -f docker-compose.yml -f compose.ci.yml run --rm --no-deps -T gateway setup
docker compose -f docker-compose.yml -f compose.ci.yml up -d --no-build
for attempt in $(seq 1 30); do
  if docker compose -f docker-compose.yml -f compose.ci.yml exec -T gateway python -m gateway healthcheck; then
    python3 scripts/check-connectivity.py
    # Test a valid but incorrect master key against the actual initialized vault.
    docker compose -f docker-compose.yml -f compose.ci.yml stop
    chmod 600 secrets/master_key
    openssl rand -hex 32 > secrets/master_key
    chmod 444 secrets/master_key
    set +e
    printf 'exit\n' | timeout 60s docker compose -f docker-compose.yml -f compose.ci.yml run --rm --no-deps -T gateway setup
    result=$?
    set -e
    test "$result" -eq 1
    docker compose -f docker-compose.yml -f compose.ci.yml run --rm --no-deps -T --entrypoint python gateway -c 'from pathlib import Path; assert not list(Path("/data").rglob("insecure")), "insecure fallback created"'
    exit 0
  fi
  sleep 2
done
docker compose -f docker-compose.yml -f compose.ci.yml logs
exit 1
