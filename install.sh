#!/usr/bin/env bash
set -euo pipefail

# codegraph-mcp installer
# Installs the package globally and configures it as an MCP server
# for Claude Code, Codex CLI, Gemini CLI, and OpenCode.

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
MCP_STARTUP_TIMEOUT_SEC="${MCP_STARTUP_TIMEOUT_SEC:-30}"

configure_claude() {
    step "Configuring Claude Code..."

    if command -v claude &>/dev/null; then
        claude mcp add-json codegraph "{
            \"type\": \"stdio\",
            \"command\": \"$MCP_CMD\",
            \"args\": [\"serve\"]
        }" --scope user 2>/dev/null && info "Added to Claude Code (user scope)" || {
            warn "claude mcp add-json failed — you may need to add it manually"
            echo "  Run: claude mcp add --scope user codegraph -- $MCP_CMD serve"
        }
    else
        warn "Claude Code CLI not found; updating settings file only"
    fi

    CLAUDE_SETTINGS="$HOME/.claude/settings.json"
    mkdir -p "$(dirname "$CLAUDE_SETTINGS")"
    if [ -f "$CLAUDE_SETTINGS" ]; then
        python3 -c "
import json
path = '$CLAUDE_SETTINGS'
with open(path, encoding='utf-8') as f:
    data = json.load(f)
data.setdefault('env', {})
data['env']['MCP_TIMEOUT'] = str(int('$MCP_STARTUP_TIMEOUT_SEC') * 1000)
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null && info "Set Claude MCP timeout to ${MCP_STARTUP_TIMEOUT_SEC}s"
    fi
}

configure_codex() {
    step "Configuring Codex CLI..."

    CODEX_CONFIG="$HOME/.codex/config.toml"
    mkdir -p "$(dirname "$CODEX_CONFIG")"

    python3 -c "
from pathlib import Path
import re
path = Path('$CODEX_CONFIG')
path.parent.mkdir(parents=True, exist_ok=True)
block = (
    '[mcp_servers.codegraph]\\n'
    f'command = \"${MCP_CMD}\"\\n'
    'args = [\"serve\"]\\n'
    f'startup_timeout_sec = ${MCP_STARTUP_TIMEOUT_SEC}\\n'
)
if path.exists():
    text = path.read_text(encoding='utf-8')
else:
    text = ''
pat = r'(?ms)^\\[mcp_servers\\.codegraph\\]\\n(?:.*\\n)*?(?=^\\[|\\Z)'
if re.search(pat, text):
    text = re.sub(pat, block + '\\n', text)
else:
    if text and not text.endswith('\\n'):
        text += '\\n'
    text += '\\n' + block
path.write_text(text, encoding='utf-8')
" && info "Configured $CODEX_CONFIG (timeout ${MCP_STARTUP_TIMEOUT_SEC}s)"
}

configure_gemini() {
    step "Configuring Gemini CLI..."

    GEMINI_CONFIG="$HOME/.gemini/settings.json"
    mkdir -p "$(dirname "$GEMINI_CONFIG")"

    if [ -f "$GEMINI_CONFIG" ]; then
        python3 -c "
import json
with open('$GEMINI_CONFIG') as f:
    data = json.load(f)
data.setdefault('mcpServers', {})
data['mcpServers']['codegraph'] = {
    'command': '$MCP_CMD',
    'args': ['serve'],
    'startup_timeout_sec': int('$MCP_STARTUP_TIMEOUT_SEC'),
    'startupTimeoutSec': int('$MCP_STARTUP_TIMEOUT_SEC')
}
with open('$GEMINI_CONFIG', 'w') as f:
    json.dump(data, f, indent=2)
" && info "Configured $GEMINI_CONFIG (timeout ${MCP_STARTUP_TIMEOUT_SEC}s)"
    else
        # Create new config
        python3 -c "
import json
data = {
    'mcpServers': {
        'codegraph': {
            'command': '$MCP_CMD',
            'args': ['serve'],
            'startup_timeout_sec': int('$MCP_STARTUP_TIMEOUT_SEC'),
            'startupTimeoutSec': int('$MCP_STARTUP_TIMEOUT_SEC')
        }
    }
}
with open('$GEMINI_CONFIG', 'w') as f:
    json.dump(data, f, indent=2)
" && info "Created $GEMINI_CONFIG"
    fi
}

configure_opencode() {
    step "Configuring OpenCode..."

    OPENCODE_CONFIG="$HOME/.config/opencode/opencode.json"
    mkdir -p "$(dirname "$OPENCODE_CONFIG")"

    python3 -c "
import json
from pathlib import Path
path = Path('$OPENCODE_CONFIG')
if path.exists():
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
else:
    data = {}
data.setdefault('mcp', {})
data['mcp']['codegraph'] = {
    'type': 'local',
    'command': ['$MCP_CMD', 'serve'],
    'startup_timeout_sec': int('$MCP_STARTUP_TIMEOUT_SEC'),
    'startupTimeoutSec': int('$MCP_STARTUP_TIMEOUT_SEC'),
}
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
" && info "Configured $OPENCODE_CONFIG (timeout ${MCP_STARTUP_TIMEOUT_SEC}s)"
}

configure_claude
configure_codex
configure_gemini
configure_opencode

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
echo "  Startup timeout configured to ${MCP_STARTUP_TIMEOUT_SEC}s."
echo ""
echo "  If startup times out in your coding client:"
echo "    1. Exit the client"
echo "    2. Run in your repo: codegraph init && codegraph index --progress"
echo ""
echo "  To use with a specific repo, pass --repo-root:"
echo "    codegraph serve --repo-root /path/to/repo"
