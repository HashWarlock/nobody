# Voice Realtime

Real-time conversational AI for macOS with multiple personas and hybrid LLM routing.

## Features

- **Push-to-Talk**: Hold Cmd+Shift+T to speak, release to get AI response
- **Multiple Personas**: Switch between Assistant, Tutor, Creative, and Casual modes
- **Hybrid LLM**: Local Ollama for speed, RedPill cloud for complex tasks
- **Voice Pipeline**: Moshi MLX for low-latency STT + TTS on Apple Silicon
- **Continuous Conversation**: Maintains context across turns

## Voice Pipeline

Uses [moshi_mlx](https://github.com/kyutai-labs/moshi) for speech processing:

- **STT**: Moshi text token extraction from audio
- **TTS**: Moshi TTSModel for natural speech synthesis
- **Codec**: Mimi neural audio codec (80ms latency)
- **Optimized**: Quantized models (8-bit) for Apple Silicon

First run downloads models (~2GB). Models are cached for subsequent runs.

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
| `Cmd+Shift+T` | Push-to-talk (hold to speak, release to process) |
| `Cmd+Shift+X` | Stop/Cancel |
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
