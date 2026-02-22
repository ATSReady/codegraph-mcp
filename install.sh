#!/usr/bin/env bash
set -euo pipefail

# codegraph-mcp installer
# Installs the package globally and configures it as an MCP server
# for Claude Code, Codex CLI, and Gemini CLI.

BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}!${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; }
step()  { echo -e "\n${BOLD}$1${NC}"; }

# ── Step 1: Install the package ──────────────────────────────────────

step "Installing codegraph-mcp..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v pipx &>/dev/null; then
    pipx install "$SCRIPT_DIR" --force 2>/dev/null && info "Installed via pipx" || {
        pipx install "$SCRIPT_DIR" --force --pip-args="--no-build-isolation" 2>/dev/null && info "Installed via pipx" || {
            err "pipx install failed, falling back to pip"
            pip install --user "$SCRIPT_DIR" && info "Installed via pip --user"
        }
    }
elif command -v uv &>/dev/null; then
    uv tool install "$SCRIPT_DIR" --force 2>/dev/null && info "Installed via uv tool" || {
        pip install --user "$SCRIPT_DIR" && info "Installed via pip --user"
    }
else
    pip install --user "$SCRIPT_DIR" && info "Installed via pip --user"
fi

# Verify the command is available
if ! command -v codegraph &>/dev/null; then
    err "codegraph command not found in PATH after installation"
    echo "  You may need to add ~/.local/bin to your PATH:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    exit 1
fi

CODEGRAPH_BIN="$(command -v codegraph)"
info "codegraph binary: $CODEGRAPH_BIN"

# ── Step 2: Configure MCP clients ────────────────────────────────────

MCP_CMD="$CODEGRAPH_BIN"
MCP_ARGS='["serve"]'

configure_claude() {
    step "Configuring Claude Code..."

    if ! command -v claude &>/dev/null; then
        warn "Claude Code CLI not found, skipping"
        return
    fi

    claude mcp add-json codegraph "{
        \"type\": \"stdio\",
        \"command\": \"$MCP_CMD\",
        \"args\": [\"serve\"]
    }" --scope user 2>/dev/null && info "Added to Claude Code (user scope)" || {
        warn "claude mcp add-json failed — you may need to add it manually"
        echo "  Run: claude mcp add --scope user codegraph -- $MCP_CMD serve"
    }
}

configure_codex() {
    step "Configuring Codex CLI..."

    if ! command -v codex &>/dev/null; then
        warn "Codex CLI not found, skipping"
        return
    fi

    CODEX_CONFIG="$HOME/.codex/config.toml"
    mkdir -p "$(dirname "$CODEX_CONFIG")"

    if [ -f "$CODEX_CONFIG" ] && grep -q '\[mcp_servers\.codegraph\]' "$CODEX_CONFIG" 2>/dev/null; then
        info "Already configured in $CODEX_CONFIG"
        return
    fi

    cat >> "$CODEX_CONFIG" <<EOF

[mcp_servers.codegraph]
command = "$MCP_CMD"
args = ["serve"]
EOF
    info "Added to $CODEX_CONFIG"
}

configure_gemini() {
    step "Configuring Gemini CLI..."

    if ! command -v gemini &>/dev/null; then
        warn "Gemini CLI not found, skipping"
        return
    fi

    GEMINI_CONFIG="$HOME/.gemini/settings.json"
    mkdir -p "$(dirname "$GEMINI_CONFIG")"

    if [ -f "$GEMINI_CONFIG" ]; then
        # Check if codegraph already configured
        if python3 -c "
import json, sys
with open('$GEMINI_CONFIG') as f:
    data = json.load(f)
sys.exit(0 if 'codegraph' in data.get('mcpServers', {}) else 1)
" 2>/dev/null; then
            info "Already configured in $GEMINI_CONFIG"
            return
        fi

        # Merge into existing config
        python3 -c "
import json
with open('$GEMINI_CONFIG') as f:
    data = json.load(f)
data.setdefault('mcpServers', {})
data['mcpServers']['codegraph'] = {
    'command': '$MCP_CMD',
    'args': ['serve']
}
with open('$GEMINI_CONFIG', 'w') as f:
    json.dump(data, f, indent=2)
" && info "Added to $GEMINI_CONFIG"
    else
        # Create new config
        python3 -c "
import json
data = {
    'mcpServers': {
        'codegraph': {
            'command': '$MCP_CMD',
            'args': ['serve']
        }
    }
}
with open('$GEMINI_CONFIG', 'w') as f:
    json.dump(data, f, indent=2)
" && info "Created $GEMINI_CONFIG"
    fi
}

configure_claude
configure_codex
configure_gemini

# ── Done ──────────────────────────────────────────────────────────────

step "Installation complete!"
echo ""
echo "  Usage:"
echo "    1. cd into any git repository"
echo "    2. codegraph init        # creates .codegraph/ config"
echo "    3. codegraph index       # builds the code graph"
echo "    4. codegraph serve       # starts MCP server (used by AI clients)"
echo ""
echo "  The MCP server is now available in any configured AI client."
echo "  Each client will start codegraph automatically when needed."
echo ""
echo "  To use with a specific repo, pass --repo-root:"
echo "    codegraph serve --repo-root /path/to/repo"
