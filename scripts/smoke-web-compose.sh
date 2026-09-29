#!/bin/sh
# No Proton account is accessed. Exercise the real web backend's TLS servers.
set -eu
sh scripts/init-secrets.sh
cat > compose.web.ci.yml <<'YAML'
services:
  gateway:
    image: gateway-web:ci
    pull_policy: never
YAML
compose() { docker compose -f docker-compose.yml -f compose.web.yml -f compose.web.ci.yml "$@"; }
trap 'compose down -v; rm -f compose.web.ci.yml' EXIT
compose config --quiet
compose up -d --no-build
for attempt in $(seq 1 30); do
  if compose exec -T gateway python -m gateway healthcheck; then
    python3 scripts/check-connectivity.py
    exit 0
  fi
  sleep 2
done
compose logs
exit 1
