#!/usr/bin/env bash
set -euo pipefail

echo "Starting MongoDB MCP Server..."

# ---- Load environment variables ----
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
else
  echo "❌ ERROR: .env file not found"
  exit 1
fi

: "${MDB_MCP_CONNECTION_STRING:?Missing MDB_MCP_CONNECTION_STRING}"
: "${MDB_MCP_HTTP_PORT:?Missing MDB_MCP_HTTP_PORT}"

MCP_HOST="127.0.0.1"
MCP_PORT="${MDB_MCP_HTTP_PORT}"

WAIT_SECONDS="${MCP_STARTUP_WAIT_SECONDS:-30}"
SLEEP_INTERVAL=1

echo "Configuration:"
echo "  MongoDB connection: user-managed (no temp users)"
echo "  Transport:          ${MDB_MCP_TRANSPORT:-http}"
echo "  MCP address:        ${MCP_HOST}:${MCP_PORT}"
echo "  Startup timeout:    ${WAIT_SECONDS}s"
echo ""

if nc -z "${MCP_HOST}" "${MCP_PORT}" >/dev/null 2>&1; then
  echo "✅ MCP server already running on ${MCP_HOST}:${MCP_PORT}"
  SERVER_PID="$(lsof -tiTCP:${MCP_PORT} -sTCP:LISTEN | head -n 1 || true)"
  echo "Server PID: ${SERVER_PID}"
  echo "Press Ctrl+C to stop the server."
  trap 'kill "${SERVER_PID}" >/dev/null 2>&1 || true' INT TERM
  while kill -0 "${SERVER_PID}" >/dev/null 2>&1; do sleep 1; done
  exit 0
fi

# ---- Start MCP server ----
npx -y mongodb-mcp-server@latest &
NPX_PID=$!

echo "MCP launcher started (PID=${NPX_PID})"
echo "Waiting for MCP server port to open..."

SECONDS_WAITED=0
READY=false

while [[ "${SECONDS_WAITED}" -lt "${WAIT_SECONDS}" ]]; do
  if nc -z "${MCP_HOST}" "${MCP_PORT}" >/dev/null 2>&1; then
    READY=true
    break
  fi
  sleep "${SLEEP_INTERVAL}"
  SECONDS_WAITED=$((SECONDS_WAITED + SLEEP_INTERVAL))
done

if [[ "${READY}" != "true" ]]; then
  echo ""
  echo "❌ ERROR: MCP server did not open port ${MCP_PORT} within ${WAIT_SECONDS}s"
  echo "Stopping launcher (PID=${NPX_PID})..."
  kill "${NPX_PID}" >/dev/null 2>&1 || true
  exit 1
fi

# ---- Find the real server PID listening on the port ----
SERVER_PID="$(lsof -tiTCP:${MCP_PORT} -sTCP:LISTEN | head -n 1 || true)"

if [[ -z "${SERVER_PID}" ]]; then
  echo ""
  echo "❌ ERROR: Port ${MCP_PORT} is open but could not determine listening PID."
  echo "Try: lsof -i :${MCP_PORT}"
  exit 1
fi

echo ""
echo "✅ MongoDB MCP Server is running and accepting connections"
echo "   Address: ${MCP_HOST}:${MCP_PORT}"
echo "   Server PID: ${SERVER_PID}"
echo "   Launcher PID: ${NPX_PID}"
echo ""
echo "Press Ctrl+C to stop the server."

# If Ctrl+C happens, stop the server PID (best effort)
cleanup() {
  echo ""
  echo "Stopping MCP server (PID=${SERVER_PID})..."
  kill "${SERVER_PID}" >/dev/null 2>&1 || true
}
trap cleanup INT TERM

# ---- Stay attached to the server process ----
# Keep script alive until server exits (PID may not be our child)
while kill -0 "${SERVER_PID}" >/dev/null 2>&1; do
  sleep 1
done

echo "MCP server process exited."
