# Voice Realtime - Conversational AI Design

Real-time conversational AI for macOS using Unmute (Kyutai) with multiple personas and hybrid LLM routing.

## Overview

Build a real-time voice conversation system using Unmute as the foundation, featuring:
- Multiple personas with different voices, LLMs, and personalities
- Hybrid LLM routing (local Ollama + RedPill API)
- Toggle activation with silence detection
- Continuous conversation flow
- Sub-1-second latency via Kyutai's streaming architecture

**Target hardware:** M4 Max Mac (128GB unified memory)

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         HAMMERSPOON                               │
│  Cmd+Shift+D (toggle)  Cmd+Shift+X (stop)  Cmd+Shift+1-4 (persona)│
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      PERSONA MANAGER                              │
│  - Loads persona config (voice, LLM, system prompt)              │
│  - Manages conversation state                                     │
│  - Routes to appropriate LLM                                      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                          UNMUTE                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │  Kyutai STT │───►│  LLM Router │───►│  Kyutai TTS │          │
│  │  (streaming)│    │             │    │  (streaming)│          │
│  └─────────────┘    └──────┬──────┘    └─────────────┘          │
│                            │                                      │
│              ┌─────────────┴─────────────┐                       │
│              ▼                           ▼                       │
│     ┌─────────────┐             ┌─────────────┐                  │
│     │   Ollama    │             │   RedPill   │                  │
│     │  (local)    │             │   (cloud)   │                  │
│     │ llama3.1:8b │             │ z-ai/glm-4.6│                  │
│     └─────────────┘             └─────────────┘                  │
└──────────────────────────────────────────────────────────────────┘
```

## Personas

Four selectable personas with different configurations:

```yaml
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

## File Structure

```
~/voice-realtime/
├── config.py              # Central configuration
├── personas.yaml          # Persona definitions (voices, prompts, LLM routing)
├── main.py                # Entry point, orchestrates components
├── conversation.py        # Conversation loop, turn management
├── llm_router.py          # Routes to Ollama or RedPill based on persona
├── persona_manager.py     # Loads/switches personas, manages state
├── hotkeys.lua            # Hammerspoon bindings
├── setup.sh               # Installation script
├── requirements.txt       # Python dependencies
├── voices/                # Custom voice samples for cloning
│   ├── tutor.wav
│   ├── creative.wav
│   └── casual.wav
└── README.md
```

**Design decisions:**
- **YAML for personas** - Easy to edit without touching code
- **Separate llm_router.py** - Abstracts Ollama vs RedPill API differences
- **voices/ directory** - 10-second samples for Kyutai voice cloning
- **Hammerspoon integration** - Reuses sup-mac hotkey approach

## Conversation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      CONVERSATION FLOW                          │
└─────────────────────────────────────────────────────────────────┘

  [Idle State]
       │
       ▼
  Cmd+Shift+D (toggle) ──────────────────────────────────────┐
       │                                                      │
       ▼                                                      │
  ┌─────────────┐                                            │
  │  LISTENING  │◄───────────────────────────────────────┐   │
  │  (Kyutai    │                                        │   │
  │   STT)      │                                        │   │
  └──────┬──────┘                                        │   │
         │                                               │   │
         ▼                                               │   │
  Silence detected (1.5s)                                │   │
  OR Cmd+Shift+D pressed                                 │   │
         │                                               │   │
         ▼                                               │   │
  ┌─────────────┐                                        │   │
  │  THINKING   │  Route to LLM based on persona         │   │
  │  (LLM)      │  - Ollama for assistant/casual         │   │
  └──────┬──────┘  - RedPill for tutor/creative          │   │
         │                                               │   │
         ▼                                               │   │
  ┌─────────────┐                                        │   │
  │  SPEAKING   │  Kyutai TTS with persona voice         │   │
  │  (Kyutai    │  Streaming audio output                │   │
  │   TTS)      │                                        │   │
  └──────┬──────┘                                        │   │
         │                                               │   │
         ▼                                               │   │
  Speech complete ───► Auto-return to LISTENING ─────────┘   │
                                                             │
  Cmd+Shift+X (stop) ─► Return to Idle ◄─────────────────────┘
```

**Flow details:**
1. **Toggle activation** - Cmd+Shift+D starts conversation mode, enters LISTENING
2. **Hybrid turn detection** - Silence (1.5s) OR manual toggle to end turn
3. **Continuous mode** - After AI speaks, auto-returns to LISTENING
4. **Clean exit** - Cmd+Shift+X stops everything and returns to idle
5. **Persona switch** - Cmd+Shift+1-4 can switch personas mid-conversation

## Error Handling

### Network Failures
- **Ollama down** - Show notification "Ollama not running", fall back to idle
- **RedPill API error** - Retry once, then notify "Cloud unavailable, switching to local" and temporarily route to Ollama
- **No internet** - Personas using RedPill gracefully degrade to local Ollama model

### Audio Issues
- **No microphone** - Notification on startup, prevent entering LISTENING state
- **No audio output** - Notification, continue conversation in text-only mode (write to file)
- **Voice clone file missing** - Fall back to Kyutai's default voice

### Conversation Edge Cases
- **User silent for 10s in LISTENING** - Auto-exit to idle with notification
- **LLM timeout (30s)** - Cancel request, notify user, return to LISTENING
- **Interrupt during SPEAKING** - Cmd+Shift+X immediately stops TTS, returns to idle
- **Persona switch mid-speech** - Queue the switch, apply after current response completes

### State Recovery
- **Crash recovery** - On restart, check for stale PID files and clean up
- **Conversation history** - Keep last 10 turns in memory per session (not persisted)

### Notifications
- Use macOS native notifications via Hammerspoon's `hs.notify`
- Brief, non-blocking alerts for state changes and errors

## Dependencies & Setup

### Python Dependencies
```
unmute              # Kyutai voice pipeline
ollama              # Local LLM client
httpx               # Async HTTP for RedPill API
pyyaml              # Persona configuration
sounddevice         # Audio I/O
numpy               # Audio processing
```

### System Requirements
- Python 3.12 (MLX compatibility)
- Ollama installed and running (`ollama serve`)
- Hammerspoon for hotkeys
- ~2GB disk for Kyutai models (downloaded on first run)
- RedPill API key in environment variable `REDPILL_API_KEY`

### Setup Flow
```bash
./setup.sh
# 1. Install Python 3.12 if needed
# 2. Create ~/voice-env venv
# 3. Install Python packages
# 4. Install Hammerspoon config
# 5. Check Ollama is installed
# 6. Prompt for REDPILL_API_KEY
# 7. Download Kyutai models (first run)
```

### First Run Experience
1. User runs `./setup.sh`
2. Grants Accessibility + Microphone permissions
3. Adds `REDPILL_API_KEY` to shell profile
4. Presses Cmd+Shift+D to start first conversation
5. Models download (~2GB), then conversation begins

## Hotkeys Summary

| Hotkey | Action |
|--------|--------|
| `Cmd+Shift+D` | Toggle conversation (start/end turn) |
| `Cmd+Shift+X` | Stop and return to idle |
| `Cmd+Shift+1` | Switch to Assistant persona |
| `Cmd+Shift+2` | Switch to Tutor persona |
| `Cmd+Shift+3` | Switch to Creative persona |
| `Cmd+Shift+4` | Switch to Casual persona |
| `Cmd+Shift+R` | Reload Hammerspoon config |

## Technology Stack

| Component | Technology | Notes |
|-----------|------------|-------|
| Voice Pipeline | Unmute (Kyutai) | STT + TTS with <1s latency |
| STT | Kyutai STT | 1B/2.6B models, streaming |
| TTS | Kyutai TTS | 1.6B model, voice cloning |
| Local LLM | Ollama | llama3.1:8b for fast responses |
| Cloud LLM | RedPill API | z-ai/glm-4.6 for complex tasks |
| Hotkeys | Hammerspoon | macOS automation |
| ML Framework | MLX | Apple Silicon optimized |
