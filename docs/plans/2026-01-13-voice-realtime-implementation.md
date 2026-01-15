# Voice Realtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a real-time conversational AI using Unmute (Kyutai) with multiple personas and hybrid LLM routing.

**Architecture:** Hammerspoon triggers Python scripts that manage conversation state. Unmute handles STT/TTS pipeline, routing to Ollama (local) or RedPill (cloud) based on active persona. Continuous conversation loop with toggle activation.

**Tech Stack:** Python 3.12, Unmute (Kyutai), Ollama, RedPill API, Hammerspoon, sounddevice

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `config.py`
- Create: `personas.yaml`

**Step 1: Create requirements.txt**

```txt
# Voice pipeline
moshi[client]>=0.2.3

# LLM clients
ollama>=0.4.0
httpx>=0.27.0

# Configuration
pyyaml>=6.0

# Audio
sounddevice>=0.5.0
numpy>=1.26.0
```

**Step 2: Create config.py**

```python
"""Central configuration for voice-realtime."""

import os
from pathlib import Path

# Directories
PROJECT_DIR = Path(__file__).parent
VOICES_DIR = PROJECT_DIR / "voices"
TEMP_DIR = Path("/tmp/claude/voice-realtime")

# Ensure directories exist
TEMP_DIR.mkdir(parents=True, exist_ok=True)
VOICES_DIR.mkdir(exist_ok=True)

# PID files for process tracking
MAIN_PID_FILE = TEMP_DIR / "main.pid"

# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 1

# Conversation settings
SILENCE_THRESHOLD_SEC = 1.5
IDLE_TIMEOUT_SEC = 10.0
LLM_TIMEOUT_SEC = 30.0

# API configuration
REDPILL_API_KEY = os.environ.get("REDPILL_API_KEY", "")
REDPILL_BASE_URL = "https://api.redpill.ai/v1"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Persona config file
PERSONAS_FILE = PROJECT_DIR / "personas.yaml"
```

**Step 3: Create personas.yaml**

```yaml
default_persona: assistant

personas:
  assistant:
    name: "Assistant"
    hotkey: "cmd+shift+1"
    llm:
      provider: "ollama"
      model: "llama3.1:8b"
    voice: "default"
    system_prompt: |
      You are a concise, helpful assistant. Give brief, actionable answers.
      Optimize for speed - short sentences, no fluff.

  tutor:
    name: "Tutor"
    hotkey: "cmd+shift+2"
    llm:
      provider: "redpill"
      model: "z-ai/glm-4.6"
    voice: "cloned_tutor"
    system_prompt: |
      You are a patient tutor who explains concepts clearly.
      Use analogies and examples. Check for understanding.
      Ask follow-up questions to deepen learning.

  creative:
    name: "Creative Partner"
    hotkey: "cmd+shift+3"
    llm:
      provider: "redpill"
      model: "z-ai/glm-4.6"
    voice: "cloned_creative"
    system_prompt: |
      You are a creative collaborator who builds on ideas.
      Offer alternatives, ask "what if", and explore possibilities.
      Be enthusiastic but constructive.

  casual:
    name: "Buddy"
    hotkey: "cmd+shift+4"
    llm:
      provider: "ollama"
      model: "llama3.1:8b"
    voice: "cloned_casual"
    system_prompt: |
      You are a friendly companion for casual conversation.
      Be warm, use humor, share opinions. Keep it natural and relaxed.
```

**Step 4: Commit setup files**

```bash
git add requirements.txt config.py personas.yaml
git commit -m "feat: add project configuration and persona definitions"
```

---

## Task 2: Persona Manager

**Files:**
- Create: `persona_manager.py`
- Create: `tests/test_persona_manager.py`

**Step 1: Write failing test for persona loading**

```python
"""Tests for persona manager."""

import pytest
from pathlib import Path


def test_load_personas_from_yaml():
    """Should load all personas from YAML file."""
    from persona_manager import PersonaManager

    manager = PersonaManager()

    assert "assistant" in manager.personas
    assert "tutor" in manager.personas
    assert "creative" in manager.personas
    assert "casual" in manager.personas


def test_get_default_persona():
    """Should return the default persona on init."""
    from persona_manager import PersonaManager

    manager = PersonaManager()
    persona = manager.get_current()

    assert persona["name"] == "Assistant"
    assert persona["llm"]["provider"] == "ollama"


def test_switch_persona():
    """Should switch to a different persona."""
    from persona_manager import PersonaManager

    manager = PersonaManager()
    manager.switch("tutor")
    persona = manager.get_current()

    assert persona["name"] == "Tutor"
    assert persona["llm"]["provider"] == "redpill"
    assert persona["llm"]["model"] == "z-ai/glm-4.6"


def test_switch_invalid_persona():
    """Should raise error for invalid persona."""
    from persona_manager import PersonaManager

    manager = PersonaManager()

    with pytest.raises(ValueError, match="Unknown persona"):
        manager.switch("nonexistent")
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/hashwarlock/voice-env/.worktrees/voice-realtime && python -m pytest tests/test_persona_manager.py -v`
Expected: FAIL with "No module named 'persona_manager'"

**Step 3: Write persona_manager.py**

```python
"""Persona manager for loading and switching between conversation personas."""

import yaml
from pathlib import Path
from typing import Any

import config


class PersonaManager:
    """Manages persona loading and switching."""

    def __init__(self, personas_file: Path | None = None):
        """Load personas from YAML file.

        Args:
            personas_file: Path to personas YAML. Defaults to config.PERSONAS_FILE.
        """
        self.personas_file = personas_file or config.PERSONAS_FILE
        self._load_personas()
        self.current_persona_id = self.default_persona

    def _load_personas(self) -> None:
        """Load personas from YAML file."""
        with open(self.personas_file) as f:
            data = yaml.safe_load(f)

        self.default_persona = data.get("default_persona", "assistant")
        self.personas = data.get("personas", {})

    def get_current(self) -> dict[str, Any]:
        """Get the currently active persona configuration.

        Returns:
            Persona configuration dict with name, llm, voice, system_prompt.
        """
        return self.personas[self.current_persona_id]

    def switch(self, persona_id: str) -> dict[str, Any]:
        """Switch to a different persona.

        Args:
            persona_id: ID of persona to switch to (e.g., "tutor", "creative").

        Returns:
            The new persona configuration.

        Raises:
            ValueError: If persona_id is not found.
        """
        if persona_id not in self.personas:
            raise ValueError(f"Unknown persona: {persona_id}")

        self.current_persona_id = persona_id
        return self.get_current()

    def list_personas(self) -> list[str]:
        """List all available persona IDs.

        Returns:
            List of persona ID strings.
        """
        return list(self.personas.keys())
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/hashwarlock/voice-env/.worktrees/voice-realtime && python -m pytest tests/test_persona_manager.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add persona_manager.py tests/test_persona_manager.py
git commit -m "feat: add persona manager with YAML loading and switching"
```

---

## Task 3: LLM Router

**Files:**
- Create: `llm_router.py`
- Create: `tests/test_llm_router.py`

**Step 1: Write failing tests for LLM routing**

```python
"""Tests for LLM router."""

import pytest
from unittest.mock import patch, MagicMock


def test_route_to_ollama():
    """Should route to Ollama for local provider."""
    from llm_router import LLMRouter

    router = LLMRouter()
    llm_config = {"provider": "ollama", "model": "llama3.1:8b"}

    with patch("llm_router.ollama") as mock_ollama:
        mock_ollama.chat.return_value = {"message": {"content": "Hello!"}}

        response = router.chat(
            llm_config=llm_config,
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="You are helpful."
        )

        assert response == "Hello!"
        mock_ollama.chat.assert_called_once()


def test_route_to_redpill():
    """Should route to RedPill for cloud provider."""
    from llm_router import LLMRouter

    router = LLMRouter()
    llm_config = {"provider": "redpill", "model": "z-ai/glm-4.6"}

    with patch("llm_router.httpx") as mock_httpx:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from cloud!"}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_response

        response = router.chat(
            llm_config=llm_config,
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="You are helpful."
        )

        assert response == "Hello from cloud!"


def test_invalid_provider():
    """Should raise error for unknown provider."""
    from llm_router import LLMRouter

    router = LLMRouter()
    llm_config = {"provider": "unknown", "model": "some-model"}

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        router.chat(
            llm_config=llm_config,
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="Test"
        )
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/hashwarlock/voice-env/.worktrees/voice-realtime && python -m pytest tests/test_llm_router.py -v`
Expected: FAIL with "No module named 'llm_router'"

**Step 3: Write llm_router.py**

```python
"""LLM router for directing requests to Ollama or RedPill."""

from typing import Any

import httpx
import ollama

import config


class LLMRouter:
    """Routes LLM requests to appropriate provider."""

    def __init__(self):
        """Initialize router with API configurations."""
        self.redpill_api_key = config.REDPILL_API_KEY
        self.redpill_base_url = config.REDPILL_BASE_URL
        self.ollama_host = config.OLLAMA_HOST
        self.timeout = config.LLM_TIMEOUT_SEC

    def chat(
        self,
        llm_config: dict[str, str],
        messages: list[dict[str, str]],
        system_prompt: str
    ) -> str:
        """Send chat request to appropriate LLM provider.

        Args:
            llm_config: Dict with 'provider' and 'model' keys.
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: System prompt for the conversation.

        Returns:
            The assistant's response text.

        Raises:
            ValueError: If provider is unknown.
        """
        provider = llm_config["provider"]
        model = llm_config["model"]

        if provider == "ollama":
            return self._chat_ollama(model, messages, system_prompt)
        elif provider == "redpill":
            return self._chat_redpill(model, messages, system_prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _chat_ollama(
        self,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str
    ) -> str:
        """Send request to local Ollama instance."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        response = ollama.chat(
            model=model,
            messages=full_messages
        )

        return response["message"]["content"]

    def _chat_redpill(
        self,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str
    ) -> str:
        """Send request to RedPill API."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        response = httpx.post(
            f"{self.redpill_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.redpill_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": full_messages
            },
            timeout=self.timeout
        )
        response.raise_for_status()

        return response.json()["choices"][0]["message"]["content"]
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/hashwarlock/voice-env/.worktrees/voice-realtime && python -m pytest tests/test_llm_router.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add llm_router.py tests/test_llm_router.py
git commit -m "feat: add LLM router for Ollama and RedPill"
```

---

## Task 4: Conversation State Machine

**Files:**
- Create: `conversation.py`
- Create: `tests/test_conversation.py`

**Step 1: Write failing tests for conversation states**

```python
"""Tests for conversation state machine."""

import pytest
from unittest.mock import MagicMock, patch


def test_initial_state_is_idle():
    """Conversation should start in IDLE state."""
    from conversation import Conversation, State

    conv = Conversation(persona_manager=MagicMock(), llm_router=MagicMock())

    assert conv.state == State.IDLE


def test_toggle_from_idle_starts_listening():
    """Toggle from IDLE should transition to LISTENING."""
    from conversation import Conversation, State

    conv = Conversation(persona_manager=MagicMock(), llm_router=MagicMock())
    conv.toggle()

    assert conv.state == State.LISTENING


def test_toggle_from_listening_starts_thinking():
    """Toggle from LISTENING should transition to THINKING."""
    from conversation import Conversation, State

    mock_persona = MagicMock()
    mock_persona.get_current.return_value = {
        "llm": {"provider": "ollama", "model": "test"},
        "system_prompt": "test"
    }

    conv = Conversation(persona_manager=mock_persona, llm_router=MagicMock())
    conv.state = State.LISTENING
    conv.current_transcript = "Hello"
    conv.toggle()

    assert conv.state == State.THINKING


def test_stop_returns_to_idle():
    """Stop from any state should return to IDLE."""
    from conversation import Conversation, State

    conv = Conversation(persona_manager=MagicMock(), llm_router=MagicMock())

    for state in [State.LISTENING, State.THINKING, State.SPEAKING]:
        conv.state = state
        conv.stop()
        assert conv.state == State.IDLE


def test_message_history_maintained():
    """Conversation should maintain message history."""
    from conversation import Conversation, State

    conv = Conversation(persona_manager=MagicMock(), llm_router=MagicMock())

    conv.add_user_message("Hello")
    conv.add_assistant_message("Hi there!")

    assert len(conv.messages) == 2
    assert conv.messages[0] == {"role": "user", "content": "Hello"}
    assert conv.messages[1] == {"role": "assistant", "content": "Hi there!"}
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/hashwarlock/voice-env/.worktrees/voice-realtime && python -m pytest tests/test_conversation.py -v`
Expected: FAIL with "No module named 'conversation'"

**Step 3: Write conversation.py**

```python
"""Conversation state machine for managing voice interaction flow."""

from enum import Enum, auto
from typing import Any

from persona_manager import PersonaManager
from llm_router import LLMRouter


class State(Enum):
    """Conversation states."""
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()


class Conversation:
    """Manages conversation state and message history."""

    MAX_HISTORY = 10  # Keep last N turn pairs

    def __init__(self, persona_manager: PersonaManager, llm_router: LLMRouter):
        """Initialize conversation.

        Args:
            persona_manager: Manager for persona configuration.
            llm_router: Router for LLM requests.
        """
        self.persona_manager = persona_manager
        self.llm_router = llm_router
        self.state = State.IDLE
        self.messages: list[dict[str, str]] = []
        self.current_transcript = ""

    def toggle(self) -> State:
        """Toggle conversation state.

        IDLE -> LISTENING
        LISTENING -> THINKING (if transcript exists)

        Returns:
            New state after toggle.
        """
        if self.state == State.IDLE:
            self.state = State.LISTENING
            self.current_transcript = ""
        elif self.state == State.LISTENING:
            if self.current_transcript:
                self.state = State.THINKING

        return self.state

    def stop(self) -> State:
        """Stop conversation and return to idle.

        Returns:
            IDLE state.
        """
        self.state = State.IDLE
        self.current_transcript = ""
        return self.state

    def add_user_message(self, content: str) -> None:
        """Add user message to history.

        Args:
            content: The user's message text.
        """
        self.messages.append({"role": "user", "content": content})
        self._trim_history()

    def add_assistant_message(self, content: str) -> None:
        """Add assistant message to history.

        Args:
            content: The assistant's response text.
        """
        self.messages.append({"role": "assistant", "content": content})
        self._trim_history()

    def _trim_history(self) -> None:
        """Trim message history to MAX_HISTORY turn pairs."""
        max_messages = self.MAX_HISTORY * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    def get_response(self) -> str:
        """Get LLM response for current conversation.

        Returns:
            Assistant response text.
        """
        persona = self.persona_manager.get_current()

        response = self.llm_router.chat(
            llm_config=persona["llm"],
            messages=self.messages,
            system_prompt=persona["system_prompt"]
        )

        return response

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.messages = []
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/hashwarlock/voice-env/.worktrees/voice-realtime && python -m pytest tests/test_conversation.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add conversation.py tests/test_conversation.py
git commit -m "feat: add conversation state machine with history"
```

---

## Task 5: Hammerspoon Hotkeys

**Files:**
- Create: `hotkeys.lua`

**Step 1: Write hotkeys.lua**

```lua
-- Voice Realtime - Hammerspoon Hotkey Configuration
-- Provides hotkeys for conversation control and persona switching

local voiceRealtime = {}

-- Configuration
local PYTHON = os.getenv("HOME") .. "/voice-env/bin/python"
local SCRIPT_DIR = os.getenv("HOME") .. "/voice-realtime"
local MAIN_SCRIPT = SCRIPT_DIR .. "/main.py"
local TEMP_DIR = "/tmp/claude/voice-realtime"

-- State tracking
local conversationTask = nil

-- Helper function to show notification
local function notify(title, text)
    hs.notify.new({title = title, informativeText = text}):send()
end

-- Helper function to run command
local function runCommand(args)
    local task = hs.task.new(PYTHON, function(exitCode, stdOut, stdErr)
        if exitCode ~= 0 then
            print("Error: " .. (stdErr or "unknown"))
        end
    end, args)
    task:start()
    return task
end

-- Toggle conversation (Cmd+Shift+D)
function voiceRealtime.toggle()
    runCommand({MAIN_SCRIPT, "toggle"})
    notify("Voice", "Toggle")
end

-- Stop conversation (Cmd+Shift+X)
function voiceRealtime.stop()
    runCommand({MAIN_SCRIPT, "stop"})
    notify("Voice", "Stopped")
end

-- Switch persona functions
function voiceRealtime.switchAssistant()
    runCommand({MAIN_SCRIPT, "persona", "assistant"})
    notify("Persona", "Assistant")
end

function voiceRealtime.switchTutor()
    runCommand({MAIN_SCRIPT, "persona", "tutor"})
    notify("Persona", "Tutor")
end

function voiceRealtime.switchCreative()
    runCommand({MAIN_SCRIPT, "persona", "creative"})
    notify("Persona", "Creative Partner")
end

function voiceRealtime.switchCasual()
    runCommand({MAIN_SCRIPT, "persona", "casual"})
    notify("Persona", "Buddy")
end

-- Bind hotkeys
hs.hotkey.bind({"cmd", "shift"}, "D", voiceRealtime.toggle)
hs.hotkey.bind({"cmd", "shift"}, "X", voiceRealtime.stop)
hs.hotkey.bind({"cmd", "shift"}, "1", voiceRealtime.switchAssistant)
hs.hotkey.bind({"cmd", "shift"}, "2", voiceRealtime.switchTutor)
hs.hotkey.bind({"cmd", "shift"}, "3", voiceRealtime.switchCreative)
hs.hotkey.bind({"cmd", "shift"}, "4", voiceRealtime.switchCasual)

-- Reload config (Cmd+Shift+R)
hs.hotkey.bind({"cmd", "shift"}, "R", function()
    hs.reload()
    notify("Hammerspoon", "Config reloaded")
end)

hs.alert.show("Voice Realtime loaded")

return voiceRealtime
```

**Step 2: Commit**

```bash
git add hotkeys.lua
git commit -m "feat: add Hammerspoon hotkey bindings"
```

---

## Task 6: Main Entry Point

**Files:**
- Create: `main.py`

**Step 1: Write main.py**

```python
#!/usr/bin/env python3
"""Main entry point for voice-realtime conversation system."""

import os
import sys
import signal
import argparse

# Ensure Homebrew binaries are in PATH
homebrew_paths = ["/opt/homebrew/bin", "/usr/local/bin"]
current_path = os.environ.get("PATH", "")
for p in homebrew_paths:
    if p not in current_path:
        os.environ["PATH"] = p + ":" + current_path
        current_path = os.environ["PATH"]

import config
from persona_manager import PersonaManager
from llm_router import LLMRouter
from conversation import Conversation, State


# Global conversation instance
conversation: Conversation | None = None


def write_pid():
    """Write current process ID for tracking."""
    with open(config.MAIN_PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def remove_pid():
    """Remove PID file on exit."""
    if config.MAIN_PID_FILE.exists():
        config.MAIN_PID_FILE.unlink()


def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    global conversation
    if conversation:
        conversation.stop()
    remove_pid()
    sys.exit(0)


def get_or_create_conversation() -> Conversation:
    """Get existing or create new conversation instance."""
    global conversation
    if conversation is None:
        persona_manager = PersonaManager()
        llm_router = LLMRouter()
        conversation = Conversation(persona_manager, llm_router)
    return conversation


def handle_toggle():
    """Handle toggle command."""
    conv = get_or_create_conversation()
    new_state = conv.toggle()
    print(f"State: {new_state.name}", file=sys.stderr)

    if new_state == State.LISTENING:
        print("Listening...", file=sys.stderr)
        # TODO: Start STT with Kyutai
    elif new_state == State.THINKING:
        print("Thinking...", file=sys.stderr)
        # Process the transcript
        conv.add_user_message(conv.current_transcript)
        response = conv.get_response()
        conv.add_assistant_message(response)
        print(f"Response: {response}", file=sys.stderr)
        # TODO: Start TTS with Kyutai


def handle_stop():
    """Handle stop command."""
    conv = get_or_create_conversation()
    conv.stop()
    print("Stopped", file=sys.stderr)


def handle_persona(persona_id: str):
    """Handle persona switch command."""
    conv = get_or_create_conversation()
    try:
        persona = conv.persona_manager.switch(persona_id)
        print(f"Switched to: {persona['name']}", file=sys.stderr)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Voice Realtime Conversation")
    parser.add_argument("command", choices=["toggle", "stop", "persona"],
                        help="Command to execute")
    parser.add_argument("persona_id", nargs="?", help="Persona ID for persona command")

    args = parser.parse_args()

    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Write PID
    write_pid()

    try:
        if args.command == "toggle":
            handle_toggle()
        elif args.command == "stop":
            handle_stop()
        elif args.command == "persona":
            if not args.persona_id:
                print("Error: persona command requires persona_id", file=sys.stderr)
                sys.exit(1)
            handle_persona(args.persona_id)
    finally:
        remove_pid()


if __name__ == "__main__":
    main()
```

**Step 2: Make executable**

```bash
chmod +x main.py
```

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add main entry point with CLI commands"
```

---

## Task 7: Setup Script

**Files:**
- Create: `setup.sh`

**Step 1: Write setup.sh**

```bash
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
echo -e "${BLUE}[1/6] Checking Homebrew...${NC}"
if ! command -v brew &> /dev/null; then
    echo -e "${YELLOW}Installing Homebrew...${NC}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
echo -e "${GREEN}Homebrew ready${NC}"

# Install dependencies
echo
echo -e "${BLUE}[2/6] Installing system dependencies...${NC}"
brew install portaudio ffmpeg 2>/dev/null || true
echo -e "${GREEN}System dependencies installed${NC}"

# Check Ollama
echo
echo -e "${BLUE}[3/6] Checking Ollama...${NC}"
if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}Installing Ollama...${NC}"
    brew install ollama
fi
echo -e "${GREEN}Ollama installed${NC}"
echo -e "${YELLOW}Make sure to run: ollama serve${NC}"

# Python environment
echo
echo -e "${BLUE}[4/6] Setting up Python environment...${NC}"
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
echo -e "${BLUE}[5/6] Configuring Hammerspoon...${NC}"
if [[ ! -d "/Applications/Hammerspoon.app" ]]; then
    brew install --cask hammerspoon
fi

mkdir -p "$HAMMERSPOON_DIR"
if [[ -f "$HAMMERSPOON_DIR/init.lua" ]]; then
    if ! grep -q "Voice Realtime" "$HAMMERSPOON_DIR/init.lua" 2>/dev/null; then
        cp "$HAMMERSPOON_DIR/init.lua" "$HAMMERSPOON_DIR/init.lua.backup"
    fi
fi
cp "$SCRIPT_DIR/hotkeys.lua" "$HAMMERSPOON_DIR/init.lua"
echo -e "${GREEN}Hammerspoon configured${NC}"

# Temp directory
echo
echo -e "${BLUE}[6/6] Creating directories...${NC}"
mkdir -p "$TEMP_DIR"
mkdir -p "$SCRIPT_DIR/voices"
echo -e "${GREEN}Directories created${NC}"

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
echo "  Cmd+Shift+D  →  Toggle conversation"
echo "  Cmd+Shift+X  →  Stop"
echo "  Cmd+Shift+1  →  Assistant (local)"
echo "  Cmd+Shift+2  →  Tutor (cloud)"
echo "  Cmd+Shift+3  →  Creative (cloud)"
echo "  Cmd+Shift+4  →  Casual (local)"
echo
```

**Step 2: Make executable**

```bash
chmod +x setup.sh
```

**Step 3: Commit**

```bash
git add setup.sh
git commit -m "feat: add setup script for installation"
```

---

## Task 8: Create tests/__init__.py and README

**Files:**
- Create: `tests/__init__.py`
- Create: `README.md`

**Step 1: Create tests/__init__.py**

```python
"""Test package for voice-realtime."""
```

**Step 2: Create README.md**

```markdown
# Voice Realtime

Real-time conversational AI for macOS with multiple personas and hybrid LLM routing.

## Features

- **Multiple Personas**: Switch between Assistant, Tutor, Creative, and Casual modes
- **Hybrid LLM**: Local Ollama for speed, RedPill cloud for complex tasks
- **Voice Pipeline**: Kyutai STT/TTS with <1s latency (coming soon)
- **Continuous Conversation**: Auto-listen after AI responds

## Requirements

- macOS (Apple Silicon recommended)
- Python 3.12
- Ollama
- Hammerspoon

## Quick Start

```bash
./setup.sh
```

## Hotkeys

| Hotkey | Action |
|--------|--------|
| `Cmd+Shift+D` | Toggle conversation |
| `Cmd+Shift+X` | Stop |
| `Cmd+Shift+1` | Switch to Assistant |
| `Cmd+Shift+2` | Switch to Tutor |
| `Cmd+Shift+3` | Switch to Creative |
| `Cmd+Shift+4` | Switch to Casual |

## Personas

- **Assistant** (Ollama): Fast, concise answers
- **Tutor** (RedPill): Patient explanations with examples
- **Creative** (RedPill): Brainstorming and ideation
- **Casual** (Ollama): Friendly conversation

## Configuration

Edit `personas.yaml` to customize personas, or add your own.

## License

MIT
```

**Step 3: Commit**

```bash
git add tests/__init__.py README.md
git commit -m "docs: add README and test package init"
```

---

## Task 9: Run All Tests

**Step 1: Install test dependencies**

```bash
source ~/voice-env/bin/activate
pip install pytest
```

**Step 2: Run full test suite**

```bash
cd /Users/hashwarlock/voice-env/.worktrees/voice-realtime
python -m pytest tests/ -v
```

Expected: All tests pass (7 tests)

**Step 3: Final commit if any fixes needed**

---

## Summary

After completing all tasks, you will have:

1. **config.py** - Central configuration
2. **personas.yaml** - Persona definitions
3. **persona_manager.py** - Loads and switches personas
4. **llm_router.py** - Routes to Ollama or RedPill
5. **conversation.py** - State machine for conversation flow
6. **main.py** - CLI entry point
7. **hotkeys.lua** - Hammerspoon bindings
8. **setup.sh** - Installation script
9. **tests/** - Unit tests for core components

**Note:** This implementation provides the foundation. Kyutai STT/TTS integration will require:
1. Installing `moshi` package when available
2. Adding audio capture/playback to conversation loop
3. Connecting Kyutai streaming to state transitions

The current implementation works with text-based testing and manual transcript input.
