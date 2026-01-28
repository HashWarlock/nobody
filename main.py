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
    response = conversation.get_response()
    conversation.add_assistant_message(response)
    print(f"AI: {response}", file=sys.stderr)

    # Synthesize and play
    print("Speaking...", file=sys.stderr)
    speech = synthesizer.synthesize(response)
    sd.play(speech, samplerate=24000)
    sd.wait()

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


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Voice Realtime Conversation")
    parser.add_argument("command", choices=["start", "stop_and_process", "stop", "persona"],
                        help="Command to execute")
    parser.add_argument("persona_id", nargs="?", help="Persona ID for persona command")

    args = parser.parse_args()

    if args.command == "start":
        handle_start()
    elif args.command == "stop_and_process":
        handle_stop_and_process()
    elif args.command == "stop":
        handle_stop()
    elif args.command == "persona":
        if not args.persona_id:
            print("Error: persona command requires persona_id", file=sys.stderr)
            sys.exit(1)
        handle_persona(args.persona_id)


if __name__ == "__main__":
    main()
