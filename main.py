#!/usr/bin/env python3
"""Main entry point for voice-realtime conversation system.

Uses file-based communication for push-to-talk since each command
is a separate process invocation from Hammerspoon.
"""

import os
import sys
import signal
import argparse
import time
import subprocess
import numpy as np

# Ensure Homebrew binaries are in PATH
homebrew_paths = ["/opt/homebrew/bin", "/usr/local/bin"]
current_path = os.environ.get("PATH", "")
for p in homebrew_paths:
    if p not in current_path:
        os.environ["PATH"] = p + ":" + current_path
        current_path = os.environ["PATH"]

import sounddevice as sd

import config
from persona_manager import PersonaManager
from llm_router import LLMRouter
from conversation import Conversation

# File paths for IPC
RECORDING_PID_FILE = config.TEMP_DIR / "recording.pid"
RECORDING_STOP_FILE = config.TEMP_DIR / "recording.stop"
AUDIO_FILE = config.TEMP_DIR / "recording.npy"
OVERLAY_STATE_FILE = config.TEMP_DIR / "harada-overlay.json"
SCRIPT_DIR = config.PROJECT_DIR


def read_pid(path):
    """Read process ID from file."""
    try:
        with open(path, 'r') as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def remove_file(path):
    """Remove file if exists."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _write_overlay_state(transcript: str, response: str, conversation):
    """Write overlay state JSON for Hammerspoon dashboard.

    Reads existing conversation history from the overlay file and appends
    the new exchange, then writes updated dashboard data.
    """
    import json
    from harada_tools import get_overlay_state

    # Load existing conversation history from overlay file
    conv_history = []
    if OVERLAY_STATE_FILE.exists():
        try:
            with open(OVERLAY_STATE_FILE) as f:
                existing = json.load(f)
                conv_history = existing.get("conversation", [])
        except (json.JSONDecodeError, IOError):
            pass

    # Append new exchange
    conv_history.append({"role": "user", "text": transcript})
    conv_history.append({"role": "assistant", "text": response})

    # Keep last 20 exchanges (40 messages) to prevent unbounded growth
    if len(conv_history) > 40:
        conv_history = conv_history[-40:]

    # Build full overlay state with dashboard data
    state = get_overlay_state(conv_history)

    # Write atomically
    tmp = str(OVERLAY_STATE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.rename(tmp, str(OVERLAY_STATE_FILE))

    print("Overlay state updated", file=sys.stderr)


def handle_start():
    """Handle start command - begin recording in background."""
    # Check if already recording
    pid = read_pid(RECORDING_PID_FILE)
    if pid:
        try:
            os.kill(pid, 0)  # Check if process exists
            print("Already recording", file=sys.stderr)
            return
        except OSError:
            pass  # Process doesn't exist, continue

    # Start recorder subprocess
    recorder_script = SCRIPT_DIR / "recorder.py"
    proc = subprocess.Popen(
        [sys.executable, str(recorder_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    print(f"Recording started (pid={proc.pid})", file=sys.stderr)


def handle_stop_and_process():
    """Handle stop_and_process command - stop recording and get response."""
    # Signal recorder to stop by creating stop file
    pid = read_pid(RECORDING_PID_FILE)
    if pid:
        # Create stop file to signal recorder
        RECORDING_STOP_FILE.touch()
        # Wait for recorder to finish saving
        for _ in range(50):  # 5 seconds max
            time.sleep(0.1)
            if not RECORDING_PID_FILE.exists():
                break

    # Check for audio file
    if not AUDIO_FILE.exists():
        print("No audio recorded", file=sys.stderr)
        return

    # Load audio
    audio = np.load(AUDIO_FILE)
    remove_file(AUDIO_FILE)

    duration = len(audio) / 24000
    print(f"Captured {duration:.1f}s of audio", file=sys.stderr)

    if len(audio) < 4800:  # Less than 0.2 seconds
        print("Audio too short", file=sys.stderr)
        return

    # Load models (cached after first load)
    print("Loading models...", file=sys.stderr)
    from stt import WhisperTranscriber
    from tts import MoshiSynthesizer

    transcriber = WhisperTranscriber(model="distil-medium.en")  # Fast & accurate for English
    synthesizer = MoshiSynthesizer()

    # Transcribe
    print("Transcribing...", file=sys.stderr)
    transcript = transcriber.transcribe(audio)

    if not transcript.strip():
        print("No speech detected", file=sys.stderr)
        return

    print(f"You said: {transcript}", file=sys.stderr)

    # Get LLM response
    print("Getting response...", file=sys.stderr)
    persona_manager = PersonaManager()
    llm_router = LLMRouter()
    conversation = Conversation(persona_manager, llm_router)

    conversation.add_user_message(transcript)

    try:
        # Check if persona uses tool calling
        persona = persona_manager.get_current()
        print(f"Persona: {persona.get('name', 'unknown')}, tools={persona.get('enable_tools', False)}", file=sys.stderr)

        if persona.get("enable_tools") and persona.get("tools") == "harada":
            print("Using Harada tools...", file=sys.stderr)
            from harada_tools import TOOL_DEFINITIONS, execute_tool, get_overlay_state
            response = conversation.get_response_with_tools(
                tools=TOOL_DEFINITIONS,
                tool_executor=execute_tool,
            )
        else:
            response = conversation.get_response()
    except Exception as e:
        import traceback
        print(f"LLM ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        response = "Sorry, I had trouble processing that. Check the logs for details."

    conversation.add_assistant_message(response)
    print(f"AI: {response}", file=sys.stderr)

    # Write overlay state for Hammerspoon (harada persona only)
    try:
        if persona.get("enable_tools") and persona.get("tools") == "harada":
            _write_overlay_state(transcript, response, conversation)
    except Exception as e:
        print(f"Overlay state write error: {e}", file=sys.stderr)

    # Synthesize and play with streaming (starts speaking immediately)
    print("Speaking...", file=sys.stderr)
    from audio_playback import StreamingAudioPlayer
    player = StreamingAudioPlayer(sample_rate=24000)
    player.start()
    synthesizer.synthesize_streaming(response, player.add_chunk)
    player.finish()

    print("Done", file=sys.stderr)


def handle_stop():
    """Handle stop command - cancel recording."""
    pid = read_pid(RECORDING_PID_FILE)
    if pid:
        # Create stop file to signal recorder
        RECORDING_STOP_FILE.touch()
        # Wait briefly for it to stop
        for _ in range(20):
            time.sleep(0.1)
            if not RECORDING_PID_FILE.exists():
                break
    remove_file(RECORDING_PID_FILE)
    remove_file(RECORDING_STOP_FILE)
    remove_file(AUDIO_FILE)
    print("Stopped", file=sys.stderr)


def handle_persona(persona_id: str):
    """Handle persona switch command."""
    persona_manager = PersonaManager()
    try:
        persona = persona_manager.switch(persona_id)
        print(f"Switched to: {persona['name']}", file=sys.stderr)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_dictate():
    """Handle dictate command - transcribe and output text to stdout for typing."""
    # Signal recorder to stop by creating stop file
    pid = read_pid(RECORDING_PID_FILE)
    if pid:
        RECORDING_STOP_FILE.touch()
        for _ in range(50):  # 5 seconds max
            time.sleep(0.1)
            if not RECORDING_PID_FILE.exists():
                break

    # Check for audio file
    if not AUDIO_FILE.exists():
        print("No audio recorded", file=sys.stderr)
        return

    # Load audio
    audio = np.load(AUDIO_FILE)
    remove_file(AUDIO_FILE)

    duration = len(audio) / 24000
    print(f"Captured {duration:.1f}s of audio", file=sys.stderr)

    if len(audio) < 4800:  # Less than 0.2 seconds
        print("Audio too short", file=sys.stderr)
        return

    # Load transcriber
    print("Transcribing...", file=sys.stderr)
    from stt import WhisperTranscriber
    transcriber = WhisperTranscriber(model="distil-medium.en")

    # Transcribe
    transcript = transcriber.transcribe(audio)

    if not transcript.strip():
        print("No speech detected", file=sys.stderr)
        return

    # Output transcript to stdout (for Hammerspoon to capture and type)
    print(transcript)


def handle_speak(text: str):
    """Handle speak command - synthesize and play text."""
    if not text.strip():
        print("No text to speak", file=sys.stderr)
        return

    print(f"Speaking: {text[:50]}{'...' if len(text) > 50 else ''}", file=sys.stderr)

    # Load TTS
    from tts import MoshiSynthesizer
    from audio_playback import StreamingAudioPlayer
    synthesizer = MoshiSynthesizer()

    # Synthesize and play with streaming
    player = StreamingAudioPlayer(sample_rate=24000)
    player.start()
    synthesizer.synthesize_streaming(text, player.add_chunk)
    player.finish()

    print("Done", file=sys.stderr)


def handle_model(model_id: str | None):
    """Handle model command - list or set model."""
    from model_manager import ModelManager
    model_manager = ModelManager()

    if model_id is None or model_id == "list":
        # List all models
        print(model_manager.list_models_formatted())
        return

    if model_id == "reset":
        # Clear override, return to default
        model_manager.clear_override()
        print(f"Reset to default: {model_manager.default_model}", file=sys.stderr)
        return

    # Set model
    try:
        model = model_manager.set_model(model_id)
        print(f"Model: {model['name']} ({model_id})", file=sys.stderr)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Use 'model list' to see available models", file=sys.stderr)
        sys.exit(1)


def handle_model_json():
    """Output models as JSON for Hammerspoon chooser."""
    import json
    from model_manager import ModelManager
    model_manager = ModelManager()

    current = model_manager.get_current_model()
    models = []
    for m in model_manager.list_models():
        models.append({
            "id": m["id"],
            "name": m["name"],
            "provider": m.get("provider", ""),
            "features": m.get("features", []),
            "current": m["id"] == current
        })

    print(json.dumps(models))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Voice Realtime Conversation")
    parser.add_argument("command", choices=["start", "stop_and_process", "stop", "persona", "dictate", "speak", "model", "model_json"],
                        help="Command to execute")
    parser.add_argument("text", nargs="?", help="Text for speak command, persona ID for persona command, or model ID for model command")

    args = parser.parse_args()

    if args.command == "start":
        handle_start()
    elif args.command == "stop_and_process":
        handle_stop_and_process()
    elif args.command == "stop":
        handle_stop()
    elif args.command == "dictate":
        handle_dictate()
    elif args.command == "speak":
        # Read from argument or stdin
        text = args.text
        if not text:
            text = sys.stdin.read()
        handle_speak(text)
    elif args.command == "persona":
        if not args.text:
            print("Error: persona command requires persona_id", file=sys.stderr)
            sys.exit(1)
        handle_persona(args.text)
    elif args.command == "model":
        handle_model(args.text)
    elif args.command == "model_json":
        handle_model_json()


if __name__ == "__main__":
    main()
