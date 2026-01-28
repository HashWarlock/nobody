#!/bin/bash
#
# Voice Realtime Setup Script
# Installs dependencies for real-time conversational AI
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$HOME/voice-env"
HAMMERSPOON_DIR="$HOME/.hammerspoon"
TEMP_DIR="/tmp/claude/voice-realtime"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Voice Realtime Setup${NC}"
echo -e "${BLUE}  Real-time Conversational AI${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo -e "${RED}Error: This script only works on macOS${NC}"
    exit 1
fi

# Check Apple Silicon
if [[ "$(uname -m)" != "arm64" ]]; then
    echo -e "${YELLOW}Warning: Optimized for Apple Silicon (M1/M2/M3/M4)${NC}"
fi

# Check Homebrew
echo -e "${BLUE}[1/8] Checking Homebrew...${NC}"
if ! command -v brew &> /dev/null; then
    echo -e "${YELLOW}Installing Homebrew...${NC}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
echo -e "${GREEN}Homebrew ready${NC}"

# Install dependencies
echo
echo -e "${BLUE}[2/8] Installing system dependencies...${NC}"
brew install portaudio ffmpeg 2>/dev/null || true
echo -e "${GREEN}System dependencies installed${NC}"

# Check Ollama
echo
echo -e "${BLUE}[3/8] Checking Ollama...${NC}"
if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}Installing Ollama...${NC}"
    brew install ollama
fi
echo -e "${GREEN}Ollama installed${NC}"
echo -e "${YELLOW}Make sure to run: ollama serve${NC}"

# Python environment
echo
echo -e "${BLUE}[4/8] Setting up Python environment...${NC}"
if ! command -v /opt/homebrew/bin/python3.12 &> /dev/null; then
    brew install python@3.12
fi

if [[ ! -d "$VENV_DIR" ]] || [[ ! -f "$VENV_DIR/bin/python3.12" ]]; then
    rm -rf "$VENV_DIR"
    /opt/homebrew/bin/python3.12 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet
pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
echo -e "${GREEN}Python environment ready${NC}"

# Hammerspoon
echo
echo -e "${BLUE}[5/8] Configuring Hammerspoon...${NC}"
if [[ ! -d "/Applications/Hammerspoon.app" ]]; then
    brew install --cask hammerspoon
fi

mkdir -p "$HAMMERSPOON_DIR"
# Backup existing init.lua if it's not already our config
if [[ -f "$HAMMERSPOON_DIR/init.lua" && ! -L "$HAMMERSPOON_DIR/init.lua" ]]; then
    if ! grep -q "Voice Realtime" "$HAMMERSPOON_DIR/init.lua" 2>/dev/null; then
        cp "$HAMMERSPOON_DIR/init.lua" "$HAMMERSPOON_DIR/init.lua.backup"
        echo -e "${YELLOW}Backed up existing init.lua${NC}"
    fi
fi
# Create symlink so changes to hotkeys.lua auto-apply
rm -f "$HAMMERSPOON_DIR/init.lua"
ln -s "$SCRIPT_DIR/hotkeys.lua" "$HAMMERSPOON_DIR/init.lua"
echo -e "${GREEN}Hammerspoon configured (symlinked to hotkeys.lua)${NC}"

# Temp directory and symlink
echo
echo -e "${BLUE}[6/8] Creating directories...${NC}"
mkdir -p "$TEMP_DIR"
mkdir -p "$SCRIPT_DIR/voices"

# Create symlink at ~/voice-realtime for portable path detection
VOICE_REALTIME_LINK="$HOME/voice-realtime"
if [[ ! -e "$VOICE_REALTIME_LINK" ]]; then
    ln -s "$SCRIPT_DIR" "$VOICE_REALTIME_LINK"
    echo -e "${GREEN}Created symlink: ~/voice-realtime -> $SCRIPT_DIR${NC}"
elif [[ -L "$VOICE_REALTIME_LINK" ]]; then
    # Update existing symlink if it points elsewhere
    CURRENT_TARGET=$(readlink "$VOICE_REALTIME_LINK")
    if [[ "$CURRENT_TARGET" != "$SCRIPT_DIR" ]]; then
        rm "$VOICE_REALTIME_LINK"
        ln -s "$SCRIPT_DIR" "$VOICE_REALTIME_LINK"
        echo -e "${YELLOW}Updated symlink: ~/voice-realtime -> $SCRIPT_DIR${NC}"
    fi
fi
echo -e "${GREEN}Directories created${NC}"

# Download Moshi models
echo
echo -e "${BLUE}[7/8] Downloading Moshi STT model (~8GB)...${NC}"
echo -e "${YELLOW}This may take a while on first run${NC}"
if command -v hf &> /dev/null; then
    hf download kyutai/moshiko-mlx-q8 --quiet || {
        echo -e "${YELLOW}Download interrupted. Run 'hf download kyutai/moshiko-mlx-q8' to resume${NC}"
    }
    echo -e "${GREEN}STT model ready${NC}"
else
    echo -e "${YELLOW}hf CLI not found. Install with: pip install huggingface_hub[cli]${NC}"
    echo -e "${YELLOW}Then run: hf download kyutai/moshiko-mlx-q8${NC}"
fi

echo
echo -e "${BLUE}[8/8] Downloading Moshi TTS model (~385MB)...${NC}"
if command -v hf &> /dev/null; then
    hf download kyutai/tts-1.6b-en_fr --quiet || {
        echo -e "${YELLOW}Download interrupted. Run 'hf download kyutai/tts-1.6b-en_fr' to resume${NC}"
    }
    hf download kyutai/tts-voices --quiet || {
        echo -e "${YELLOW}Download interrupted. Run 'hf download kyutai/tts-voices' to resume${NC}"
    }
    echo -e "${GREEN}TTS models ready${NC}"
else
    echo -e "${YELLOW}Run manually after installing hf CLI:${NC}"
    echo -e "${YELLOW}  hf download kyutai/tts-1.6b-en_fr${NC}"
    echo -e "${YELLOW}  hf download kyutai/tts-voices${NC}"
fi

# Check RedPill API key
echo
if [[ -z "$REDPILL_API_KEY" ]]; then
    echo -e "${YELLOW}Note: REDPILL_API_KEY not set${NC}"
    echo "Add to your shell profile:"
    echo "  export REDPILL_API_KEY='your-key-here'"
fi

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${BLUE}Next steps:${NC}"
echo "1. Grant Accessibility permissions to Hammerspoon"
echo "2. Grant Microphone permissions to Terminal"
echo "3. Start Ollama: ollama serve"
echo "4. Pull model: ollama pull llama3.1:8b"
echo "5. Set REDPILL_API_KEY if using cloud personas"
echo "6. Open Hammerspoon"
echo
echo -e "${BLUE}Hotkeys:${NC}"
echo "  Cmd+Shift+T  →  Push-to-talk (hold to speak)"
echo "  Cmd+Shift+X  →  Stop/Cancel"
echo "  Cmd+Shift+1  →  Assistant (local)"
echo "  Cmd+Shift+2  →  Tutor (cloud)"
echo "  Cmd+Shift+3  →  Creative (cloud)"
echo "  Cmd+Shift+4  →  Casual (local)"
echo
