#!/usr/bin/env bash
set -euo pipefail
image_name="${1:-pluggy-finance-mcp:local}"
container_id="$(docker run -d --rm -p 127.0.0.1::8080 \
  -e PLUGGY_CLIENT_ID=synthetic-client \
  -e PLUGGY_CLIENT_SECRET=synthetic-secret \
  -e MCP_PUBLIC_URL=https://localhost/mcp \
  -e MCP_OAUTH_ISSUER_URL=https://identity.example.invalid \
  -e MCP_OAUTH_ALLOWED_SUBJECT=synthetic-subject \
  -e MCP_OAUTH_ALLOWED_CLIENT_IDS=synthetic-client \
  "$image_name")"
trap 'docker stop "$container_id" >/dev/null 2>&1 || true' EXIT
container_port="$(docker port "$container_id" 8080/tcp | sed 's/.*://')"
for attempt in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$container_port/healthz" >/dev/null; then break; fi
  sleep 1
done
curl -fsS "http://127.0.0.1:$container_port/readyz" >/dev/null
status="$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$container_port/mcp")"
test "$status" = 401
curl -fsS "http://127.0.0.1:$container_port/.well-known/oauth-protected-resource/mcp" \
  | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data["scopes_supported"] == ["pluggy:access"]'
test "$(docker exec "$container_id" id -u)" != 0
printf 'Container OAuth boundary smoke passed (no Pluggy data requested).\n'
