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
LLM_TIMEOUT_SEC = 120.0  # Increased for slower cloud models

# API configuration
REDPILL_API_KEY = os.environ.get("REDPILL_API_KEY", "")
REDPILL_BASE_URL = "https://api.redpill.ai/v1"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Persona config file
PERSONAS_FILE = PROJECT_DIR / "personas.yaml"
