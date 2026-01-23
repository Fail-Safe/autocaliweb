#!/bin/bash
# Setup script for kobosim with its own venv
# Prefers pyenv, falls back to system Python or brew

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQUIRED_MINOR=12
PYTHON=""
PYTHON_VERSION=""

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_success() { echo -e "${GREEN}✓${NC} $1"; }
echo_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
echo_error() { echo -e "${RED}✗${NC} $1"; }

check_python_version() {
    local py="$1"
    if command -v "$py" &> /dev/null; then
        local version=$($py -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        local major=$(echo "$version" | cut -d. -f1)
        local minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge "$REQUIRED_MINOR" ]; then
            echo "$version"
            return 0
        fi
    fi
    return 1
}

# Strategy 1: Check for pyenv
find_python_pyenv() {
    if command -v pyenv &> /dev/null; then
        echo "Checking pyenv for Python 3.${REQUIRED_MINOR}+..."

        # Check if desired version is already installed
        for version in 3.13 3.12; do
            local installed=$(pyenv versions --bare 2>/dev/null | grep "^${version}" | head -1)
            if [ -n "$installed" ]; then
                local pyenv_python="$(pyenv root)/versions/${installed}/bin/python"
                if [ -x "$pyenv_python" ]; then
                    PYTHON="$pyenv_python"
                    PYTHON_VERSION=$(check_python_version "$PYTHON")
                    if [ -n "$PYTHON_VERSION" ]; then
                        echo_success "Found pyenv Python $PYTHON_VERSION"
                        return 0
                    fi
                fi
            fi
        done

        # Offer to install via pyenv
        echo_warn "Python 3.${REQUIRED_MINOR}+ not found in pyenv"
        read -p "Install Python 3.13 via pyenv? [Y/n] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            echo "Installing Python 3.13 via pyenv (this may take a few minutes)..."
            pyenv install 3.13 -s
            PYTHON="$(pyenv root)/versions/3.13.$(pyenv versions --bare | grep '^3.13' | head -1 | cut -d. -f3)/bin/python"
            # Simpler approach - just get the path after install
            PYTHON="$(pyenv root)/versions/$(pyenv versions --bare | grep '^3.13' | head -1)/bin/python"
            if [ -x "$PYTHON" ]; then
                PYTHON_VERSION=$(check_python_version "$PYTHON")
                echo_success "Installed Python $PYTHON_VERSION via pyenv"
                return 0
            fi
        fi
    fi
    return 1
}

# Strategy 2: Check system Python paths
find_python_system() {
    echo "Checking system Python..."
    for py in python3.13 python3.12 python3; do
        PYTHON_VERSION=$(check_python_version "$py")
        if [ -n "$PYTHON_VERSION" ]; then
            PYTHON="$py"
            echo_success "Found system Python $PYTHON_VERSION ($py)"
            return 0
        fi
    done
    return 1
}

# Strategy 3: Offer brew install
find_python_brew() {
    if command -v brew &> /dev/null; then
        echo_warn "Python 3.${REQUIRED_MINOR}+ not found"
        read -p "Install Python 3.13 via Homebrew? [Y/n] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            echo "Installing Python 3.13 via Homebrew..."
            brew install python@3.13

            # Check common brew paths
            for py in /opt/homebrew/bin/python3.13 /usr/local/bin/python3.13 python3.13; do
                PYTHON_VERSION=$(check_python_version "$py")
                if [ -n "$PYTHON_VERSION" ]; then
                    PYTHON="$py"
                    echo_success "Installed Python $PYTHON_VERSION via Homebrew"
                    return 0
                fi
            done
        fi
    fi
    return 1
}

# Main Python discovery
echo "═══════════════════════════════════════════════════════════════"
echo "           kobosim setup - Python 3.${REQUIRED_MINOR}+ required"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Try strategies in order
if ! find_python_pyenv; then
    if ! find_python_system; then
        if ! find_python_brew; then
            echo ""
            echo_error "Could not find or install Python 3.${REQUIRED_MINOR}+"
            echo ""
            echo "Please install Python 3.${REQUIRED_MINOR}+ manually:"
            echo "  • pyenv:     pyenv install 3.13"
            echo "  • Homebrew:  brew install python@3.13"
            echo "  • Download:  https://www.python.org/downloads/"
            exit 1
        fi
    fi
fi

echo ""

# Create venv if needed
if [ -d "$VENV_DIR" ]; then
    # Check if existing venv has correct Python version
    if [ -x "$VENV_DIR/bin/python" ]; then
        existing_version=$("$VENV_DIR/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        if [ "$existing_version" = "$PYTHON_VERSION" ]; then
            echo_success "Using existing venv (Python $existing_version)"
        else
            echo_warn "Existing venv has Python $existing_version, recreating with $PYTHON_VERSION..."
            rm -rf "$VENV_DIR"
            $PYTHON -m venv "$VENV_DIR"
            echo_success "Created new venv with Python $PYTHON_VERSION"
        fi
    else
        rm -rf "$VENV_DIR"
        $PYTHON -m venv "$VENV_DIR"
        echo_success "Created venv with Python $PYTHON_VERSION"
    fi
else
    echo "Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
    echo_success "Created venv with Python $PYTHON_VERSION"
fi

# Activate and install
echo "Installing dependencies..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -e ".[dev]" -q
echo_success "Dependencies installed"

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                   kobosim setup complete!                     ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo "║  To activate:                                                 ║"
echo "║    source kobosim/.venv/bin/activate                          ║"
echo "║                                                               ║"
echo "║  To run:                                                      ║"
echo "║    kobosim --server URL --token TOKEN                         ║"
echo "║                                                               ║"
echo "║  Or directly:                                                 ║"
echo "║    kobosim/.venv/bin/kobosim --server URL --token TOKEN       ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
