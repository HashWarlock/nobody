"""Central configuration for voice-realtime."""

import os
from pathlib import Path

# Load .env file if it exists
def _load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value

_load_env()

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

# Moshi model configuration
MOSHI_REPO = "kyutai/moshiko-mlx-q8"  # Quantized Moshi model for STT/TTS
MOSHI_QUANTIZE = 8  # Quantization bits (4 or 8)
MOSHI_SAMPLE_RATE = 24000  # Audio sample rate

# Persona config file
PERSONAS_FILE = PROJECT_DIR / "personas.yaml"
