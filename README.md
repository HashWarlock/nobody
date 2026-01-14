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
