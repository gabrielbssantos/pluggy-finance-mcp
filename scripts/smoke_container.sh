#!/usr/bin/env bash
set -euo pipefail
image_name="${1:-pluggy-finance-mcp:local}"
smoke_token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
container_id="$(docker run -d --rm -p 127.0.0.1::8080 \
  -e PLUGGY_CLIENT_ID=synthetic-client \
  -e PLUGGY_CLIENT_SECRET=synthetic-secret \
  -e PLUGGY_ITEM_ID=00000000-0000-0000-0000-000000000001 \
  -e MCP_BEARER_TOKEN="$smoke_token" \
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
curl -fsS "http://127.0.0.1:$container_port/mcp" \
  -H "Authorization: Bearer $smoke_token" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' >/dev/null
curl -fsS "http://127.0.0.1:$container_port/mcp" \
  -H "Authorization: Bearer $smoke_token" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | python3 -c 'import json,sys; assert len(json.load(sys.stdin)["result"]["tools"]) == 18'
test "$(docker exec "$container_id" id -u)" != 0
printf 'Container HTTP smoke passed (no Pluggy data requested).\n'
