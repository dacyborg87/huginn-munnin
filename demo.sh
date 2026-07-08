#!/usr/bin/env bash
# demo.sh — One-command demo for Huginn/Muninn
# Starts the API and dashboard, injects a sample alert, then tells you what to do next.
# Stop everything when done: press Ctrl+C or run: kill $(cat /tmp/huginn-api.pid /tmp/huginn-web.pid 2>/dev/null)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$REPO_ROOT/apps/api"
WEB_DIR="$REPO_ROOT/apps/web"
API_URL="http://127.0.0.1:8000"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${GREEN}[huginn]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET}  $*"; }
error()   { echo -e "${RED}[error]${RESET} $*" >&2; }
section() { echo -e "\n${BOLD}$*${RESET}"; }

# ── Cleanup on exit ───────────────────────────────────────────────────────────
cleanup() {
  echo ""
  info "Stopping servers..."
  if [[ -f /tmp/huginn-api.pid ]]; then
    kill "$(cat /tmp/huginn-api.pid)" 2>/dev/null || true
    rm -f /tmp/huginn-api.pid
  fi
  if [[ -f /tmp/huginn-web.pid ]]; then
    kill "$(cat /tmp/huginn-web.pid)" 2>/dev/null || true
    rm -f /tmp/huginn-web.pid
  fi
  info "Done. Goodbye."
}
trap cleanup EXIT INT TERM

# ── Step 1: Check requirements ────────────────────────────────────────────────
section "1/6  Checking requirements"

if ! command -v python3.11 &>/dev/null; then
  error "Python 3.11 not found. Install it from https://python.org and try again."
  error "On Mac with Homebrew: brew install python@3.11"
  exit 1
fi
info "Python 3.11 found: $(python3.11 --version)"

if ! command -v node &>/dev/null; then
  error "Node.js not found. Install Node 22 from https://nodejs.org and try again."
  error "On Mac with Homebrew: brew install node@22"
  exit 1
fi
NODE_VERSION="$(node --version)"
info "Node.js found: $NODE_VERSION"

if ! command -v npm &>/dev/null; then
  error "npm not found. It normally ships with Node.js — reinstall Node 22."
  exit 1
fi

if ! command -v curl &>/dev/null; then
  error "curl not found. Install it with your system package manager."
  exit 1
fi

if [[ ! -d "$API_DIR" ]]; then
  error "apps/api directory not found. Are you in the huginn-muninn repo root?"
  exit 1
fi

if [[ ! -d "$WEB_DIR" ]]; then
  error "apps/web directory not found. Are you in the huginn-muninn repo root?"
  exit 1
fi

# ── Step 2: Set up Python virtualenv ─────────────────────────────────────────
section "2/6  Setting up Python environment"

cd "$API_DIR"

if [[ ! -f ".venv/bin/python" ]]; then
  info "Creating virtualenv..."
  python3.11 -m venv .venv
fi

info "Installing Python dependencies (this may take a minute the first time)..."
.venv/bin/pip install -e ".[dev]" -q

# ── Step 3: Install Node dependencies ────────────────────────────────────────
section "3/6  Installing Node dependencies"

cd "$WEB_DIR"

if [[ ! -d "node_modules" ]]; then
  info "Running npm install (this may take a minute the first time)..."
  npm install --silent
else
  info "node_modules already present, skipping npm install."
fi

# ── Step 4: Start the API ─────────────────────────────────────────────────────
section "4/6  Starting FastAPI backend"

cd "$API_DIR"

info "Starting API on $API_URL ..."
PYTHONPATH=src .venv/bin/uvicorn huginn_muninn_api.main:app \
  --host 127.0.0.1 --port 8000 \
  > /tmp/huginn-api.log 2>&1 &
echo $! > /tmp/huginn-api.pid

info "Waiting for API to be ready..."
MAX_WAIT=30
WAITED=0
until curl -sf "$API_URL/health" > /dev/null 2>&1; do
  if (( WAITED >= MAX_WAIT )); then
    error "API did not start within ${MAX_WAIT}s."
    error "Check logs: cat /tmp/huginn-api.log"
    exit 1
  fi
  sleep 1
  (( WAITED++ ))
done
info "API is ready. (${WAITED}s)"

# ── Step 5: Start the dashboard ───────────────────────────────────────────────
section "5/6  Starting Next.js dashboard"

cd "$WEB_DIR"

info "Starting dashboard on http://localhost:3000 ..."
npm run dev > /tmp/huginn-web.log 2>&1 &
echo $! > /tmp/huginn-web.pid

# ── Step 6: Inject sample alert ───────────────────────────────────────────────
section "6/6  Injecting sample Wazuh alert"

ALERT_RESPONSE="$(curl -sf -X POST "$API_URL/ingest/wazuh" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "demo-0001",
    "timestamp": "2026-06-17T15:00:00.000Z",
    "agent": { "name": "demo-endpoint-01" },
    "rule": {
      "id": "DEMO-60122",
      "level": 10,
      "description": "Synthetic repeated authentication failure pattern",
      "mitre": { "id": ["T1110", "T1078"] }
    }
  }')"

if [[ -z "$ALERT_RESPONSE" ]]; then
  warn "Alert injection got no response — the API may still be warming up. Try the curl manually:"
  warn "  curl -X POST $API_URL/ingest/wazuh -H 'Content-Type: application/json' -d '{\"id\":\"demo-0001\",\"rule\":{\"id\":\"DEMO-60122\",\"description\":\"test\",\"mitre\":{\"id\":[\"T1110\"]}},\"agent\":{\"name\":\"demo-endpoint-01\"}}'"
else
  info "Alert injected:"
  echo "$ALERT_RESPONSE" | python3.11 -c "import sys,json; d=json.load(sys.stdin); print('  events_added:', d.get('events_added',0)); print('  techniques_added:', d.get('techniques_added',0)); print('  status:', d.get('status','unknown'))"
fi

# ── Next steps ────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  Huginn/Muninn demo is running${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${GREEN}1.${RESET} Open ${BOLD}http://localhost:3000${RESET} in your browser"
echo -e "     (the dashboard may take 10–15 seconds to finish loading)"
echo ""
echo -e "  ${GREEN}2.${RESET} Look for ${BOLD}DEMO-60122${RESET} in the Recent Security Events panel"
echo -e "     (it may appear after the 30-second refresh cycle)"
echo ""
echo -e "  ${GREEN}3.${RESET} Click the alert row to open the Intelligence Detail panel"
echo ""
echo -e "  ${GREEN}4.${RESET} Review the MITRE technique (T1110 · T1078), evidence record,"
echo -e "     and any evidence gaps"
echo ""
echo -e "  ${YELLOW}To stop:${RESET} press Ctrl+C in this terminal"
echo ""

# Keep running until Ctrl+C
wait
