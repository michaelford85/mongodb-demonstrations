#!/usr/bin/env bash
set -euo pipefail

echo "Stopping MongoDB MCP Server..."

# Load env so we know which port to target (optional but helpful)
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

PORT="${MDB_MCP_HTTP_PORT:-3000}"

# Find any mongodb-mcp-server process started via npx
PIDS=$(ps aux | grep "[m]ongodb-mcp-server" | awk '{print $2}')

if [[ -z "${PIDS}" ]]; then
  echo "No mongodb-mcp-server process found."
  exit 0
fi

echo "Found MCP server process(es): ${PIDS}"
echo "Sending SIGTERM..."

kill ${PIDS}

# Optional: wait briefly and confirm shutdown
sleep 2

STILL_RUNNING=$(ps aux | grep "[m]ongodb-mcp-server" || true)

if [[ -n "${STILL_RUNNING}" ]]; then
  echo "⚠️ MCP server still running. Sending SIGKILL..."
  kill -9 ${PIDS}
else
  echo "✅ MCP server stopped cleanly."
fi