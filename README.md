# Voice Realtime

Real-time conversational AI for macOS with push-to-talk interface and multiple personas.

## Features

- **Push-to-Talk**: Hold `Cmd+Shift+T` to speak, release to get AI response
- **Push-to-Dictate**: Hold `Cmd+Shift+D` to speak, release to type at cursor
- **Read Selection**: Select text, press `Cmd+Shift+S` to hear it read aloud
- **Multiple Personas**: Switch between Assistant, Tutor, Creative, and Casual modes
- **Hybrid LLM**: RedPill GPU TEE models with cryptographic attestation
- **Fast STT**: Lightning Whisper MLX - optimized for Apple Silicon
- **Natural TTS**: Moshi neural speech synthesis
- **Continuous Conversation**: Maintains context across turns

## Requirements

- macOS with Apple Silicon (M1/M2/M3/M4)
- Python 3.12+
- [Hammerspoon](https://www.hammerspoon.org/) (for hotkeys)
- RedPill API key (get one at [redpill.ai](https://redpill.ai))

## Getting Started

### 1. Clone and Setup

```bash
git clone https://github.com/HashWarlock/nobody.git
cd nobody
./setup.sh
```

The setup script will:
- Create a Python virtual environment at `~/voice-env`
- Install all dependencies
- Symlink Hammerspoon config (auto-updates when you pull changes)
- Download required ML models (~1GB)
- Create a symlink at `~/voice-realtime`

### 2. Configure API Key

Create a `.env` file with your RedPill API key:

```bash
cp .env.example .env
# Edit .env and add your REDPILL_API_KEY
```

Or manually:
```bash
echo "REDPILL_API_KEY=your-key-here" > .env
```

### 3. Grant Permissions

- **System Settings > Privacy & Security > Accessibility**
  - Add Hammerspoon and grant access
- **System Settings > Privacy & Security > Microphone**
  - Grant access to Terminal (or your terminal app)
- **System Settings > Privacy & Security > Automation** (for dictation)
  - Allow Hammerspoon to control "System Events"

### 4. Start Using

1. Open Hammerspoon (you should see "Voice Realtime ready!" alert)
2. Hold `Cmd+Shift+T` and speak
3. Release to hear the AI response

## Hotkeys

| Hotkey | Action |
|--------|--------|
| `Cmd+Shift+T` | Push-to-talk (hold to speak, release to get AI response) |
| `Cmd+Shift+D` | Push-to-dictate (hold to speak, release to type at cursor) |
| `Cmd+Shift+S` | Read selection (highlight text, press to hear it spoken) |
| `Cmd+Shift+X` | Stop/Cancel |
| `Cmd+Shift+M` | Model picker (searchable menu to switch LLM) |
| `Cmd+Shift+1` | Switch to Assistant persona |
| `Cmd+Shift+2` | Switch to Tutor persona |
| `Cmd+Shift+3` | Switch to Creative persona |
| `Cmd+Shift+4` | Switch to Casual persona |
| `Cmd+Shift+R` | Reload Hammerspoon config |

## Personas

Configure in `personas.yaml`:

| Persona | Provider | Description |
|---------|----------|-------------|
| Assistant | RedPill | Fast, concise answers |
| Tutor | RedPill | Patient explanations with examples |
| Creative | RedPill | Brainstorming and ideation |
| Casual | Ollama | Friendly local conversation |

## Voice Pipeline

| Component | Technology | Description |
|-----------|------------|-------------|
| STT | [Lightning Whisper MLX](https://github.com/mustafaaljadery/lightning-whisper-mlx) | 10x faster than whisper.cpp |
| TTS | [Moshi MLX](https://github.com/kyutai-labs/moshi) | Neural speech synthesis |
| LLM | RedPill API | GPU TEE models with cryptographic attestation |

### STT Models

The default STT model is `distil-medium.en`. Available models:

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| tiny | 39M | Fastest | Basic |
| small | 244M | Fast | Good |
| distil-medium.en | 769M | Fast | Great (English) |
| large-v3 | 1.5B | Slower | Best |

Change in `main.py`:
```python
transcriber = WhisperTranscriber(model="distil-medium.en")
```

## Configuration

### Environment Variables

Create a `.env` file (see `.env.example`):

```bash
# Required for cloud personas
REDPILL_API_KEY=your-key-here

# Optional: Override Ollama host for local personas
OLLAMA_HOST=http://localhost:11434
```

### Changing LLM Models

Edit `personas.yaml` to change which model each persona uses:

```yaml
personas:
  assistant:
    llm:
      provider: "redpill"
      model: "deepseek/deepseek-v3.2"  # Default, strong reasoning
```

### GPU TEE Models (18 Total)

All models run in hardware-secured GPU TEE environments with cryptographic attestation.

#### Phala Network (9 models)

| Model ID | Name | Features |
|----------|------|----------|
| `deepseek/deepseek-v3.2` | DeepSeek v3.2 | Reasoning |
| `phala/uncensored-24b` | Uncensored 24B | Uncensored |
| `phala/glm-4.7-flash` | GLM 4.7 Flash | Multilingual, fast |
| `phala/qwen3-vl-30b-a3b-instruct` | Qwen3 VL 30B | Vision |
| `phala/qwen2.5-vl-72b-instruct` | Qwen 2.5 VL 72B | Vision |
| `phala/qwen-2.5-7b-instruct` | Qwen 2.5 7B | General, fast |
| `phala/gemma-3-27b-it` | Gemma 3 27B | General |
| `phala/gpt-oss-120b` | GPT OSS 120B | General |
| `phala/gpt-oss-20b` | GPT OSS 20B | General, fast |

#### Tinfoil (5 models)

| Model ID | Name | Features |
|----------|------|----------|
| `moonshotai/kimi-k2.5` | Kimi K2.5 | **Default**, reasoning |
| `moonshotai/kimi-k2-thinking` | Kimi K2 Thinking | Reasoning |
| `deepseek/deepseek-r1-0528` | DeepSeek R1 | Reasoning |
| `qwen/qwen3-coder-480b-a35b-instruct` | Qwen3 Coder 480B | Code |
| `meta-llama/llama-3.3-70b-instruct` | Llama 3.3 70B | General |

#### Chutes (1 model)

| Model ID | Name | Features |
|----------|------|----------|
| `minimax/minimax-m2.1` | MiniMax M2.1 | General |

#### Near-AI (4 models)

| Model ID | Name | Features |
|----------|------|----------|
| `deepseek/deepseek-chat-v3.1` | DeepSeek Chat v3.1 | General |
| `qwen/qwen3-30b-a3b-instruct-2507` | Qwen3 30B | General |
| `z-ai/glm-4.7` | GLM 4.7 | Multilingual |
| `z-ai/glm-4.7-flash` | GLM 4.7 Flash | Multilingual, fast |

### Which Model Should I Use?

| Use Case | Recommended Model | Why |
|----------|-------------------|-----|
| General chat | `moonshotai/kimi-k2.5` | Default, strong reasoning |
| Complex reasoning | `deepseek/deepseek-r1-0528` | Reasoning-optimized with R1 architecture |
| Long context | `moonshotai/kimi-k2-thinking` | Deep reasoning, extended thinking |
| Coding | `qwen/qwen3-coder-480b-a35b-instruct` | Code-specialized, 262k context |
| Vision tasks | `phala/qwen2.5-vl-72b-instruct` | Best vision model |
| Fast + balanced | `meta-llama/llama-3.3-70b-instruct` | Llama 3.3, good all-around |
| Uncensored | `phala/uncensored-24b` | No content restrictions |
| Multilingual | `z-ai/glm-4.7` | Strong multilingual support |

## Troubleshooting

### "launch path not accessible" error
The Python path or script path is wrong. Run `./setup.sh` again or check that `~/voice-env/bin/python` exists.

### No response from AI
Check that `REDPILL_API_KEY` is set in `.env` file.

### Transcription is wrong/gibberish
Try a larger Whisper model (e.g., `small` or `distil-medium.en`).

### Hammerspoon not responding
Reload config with `Cmd+Shift+R` or restart Hammerspoon.

### Dictation not typing
1. Check **System Settings > Privacy & Security > Automation** - Hammerspoon needs permission to control "System Events"
2. Make sure a text field is focused when you release the hotkey
3. Try `Cmd+V` manually after dictating - if text pastes, it's a permission issue

## License

MIT
