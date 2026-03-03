#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Pokémon Price & Stock Monitor — update & launch
#
#  Usage:
#    ./update.sh          # pull + restart (normal use)
#    ./update.sh --no-pull  # skip git pull (useful when testing local changes)
#
#  Ports
#    :8000  Web UI  →  http://SERVER:8000/
#    :8000  API     →  http://SERVER:8000/api/v1/
#
#  The FastAPI app serves both the web dashboard and the REST API on the same
#  port.  The MarketIntel service has its own systemd unit and its own port;
#  this script never touches it.
#
#  Systemd service name: pkmn-shopify
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$APP_DIR/.venv"
SERVICE="pkmn-shopify"
PORT=8000
GIT_BRANCH="main"
DO_PULL=true

# ── Colors ────────────────────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;34m'; N='\033[0m'
ok()   { echo -e "${G}✓ $*${N}"; }
info() { echo -e "${B}→ $*${N}"; }
warn() { echo -e "${Y}⚠ $*${N}"; }
fail() { echo -e "${R}✗ $*${N}"; exit 1; }

# ── Parse args ────────────────────────────────────────────────────────────────
for arg in "$@"; do
    [[ "$arg" == "--no-pull" ]] && DO_PULL=false
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Pokémon Price & Stock Monitor — update & launch"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
info "App dir : $APP_DIR"
info "Service : $SERVICE"
info "Port    : $PORT"
echo ""

# ── 1. Sanity checks ──────────────────────────────────────────────────────────
[[ -f "$APP_DIR/run.py" ]]          || fail "run.py not found — wrong directory?"
[[ -f "$APP_DIR/requirements.txt" ]] || fail "requirements.txt not found"
[[ -d "$VENV" ]]                    || fail ".venv not found. Run:  python3 -m venv $VENV"

# ── 2. Git pull ───────────────────────────────────────────────────────────────
if $DO_PULL; then
    info "[1/4] Pulling latest code from $GIT_BRANCH..."
    cd "$APP_DIR"
    git fetch --quiet
    git pull origin "$GIT_BRANCH" || warn "git pull failed — continuing with current code"
    ok "Code updated"
else
    warn "[1/4] Skipping git pull (--no-pull)"
fi
echo ""

# ── 3. Install / upgrade Python dependencies ──────────────────────────────────
info "[2/4] Installing Python dependencies..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
ok "Dependencies up to date"
echo ""

# ── 4. Database migrations ────────────────────────────────────────────────────
info "[3/4] Running database migrations..."
cd "$APP_DIR"
"$VENV/bin/alembic" upgrade head 2>&1 | sed 's/^/  /' || warn "Alembic returned non-zero — check above"
ok "Migrations done"
echo ""

# ── 5. Start / restart the systemd service ────────────────────────────────────
info "[4/4] Starting service..."

# Create systemd unit file if it doesn't exist yet
SERVICE_FILE="/etc/systemd/system/$SERVICE.service"
if [[ ! -f "$SERVICE_FILE" ]]; then
    warn "Systemd unit not found — creating $SERVICE_FILE (needs sudo)"
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Pokemon Price & Stock Monitor (FastAPI)
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV/bin/python $APP_DIR/run.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE"
    ok "Systemd unit created and enabled"
fi

# Restart (or start for the first time)
if sudo systemctl is-active --quiet "$SERVICE"; then
    sudo systemctl restart "$SERVICE"
    ok "Service restarted"
else
    sudo systemctl start "$SERVICE"
    ok "Service started"
fi

# ── 6. Health check ───────────────────────────────────────────────────────────
echo ""
info "Waiting for app to come up..."
for i in $(seq 1 15); do
    sleep 2
    if curl -sf "http://localhost:$PORT/api/v1/health" > /dev/null 2>&1; then
        ok "Health check passed (attempt $i)"
        break
    fi
    if [[ $i -eq 15 ]]; then
        warn "Health check did not pass after 30 s — check logs below"
        sudo journalctl -u "$SERVICE" -n 30 --no-pager
    fi
done

# ── Done ──────────────────────────────────────────────────────────────────────
SERVER_IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo -e "${G}  Done!${N}"
echo ""
echo -e "  Web UI  →  ${G}http://$SERVER_IP:$PORT/${N}"
echo -e "  API     →  ${G}http://$SERVER_IP:$PORT/api/v1/${N}"
echo -e "  Docs    →  ${G}http://$SERVER_IP:$PORT/docs${N}"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status  $SERVICE   # status"
echo "    sudo systemctl restart $SERVICE   # restart"
echo "    sudo journalctl -u $SERVICE -f    # live logs"
echo -e "${G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo ""
