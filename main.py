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
from audio_capture import AudioRecorder
from stt import MoshiTranscriber
from tts import MoshiSynthesizer
from audio_playback import AudioPlayer


# Global conversation instance
conversation: Conversation | None = None

# Global voice pipeline instances (lazy loaded)
recorder: AudioRecorder | None = None
transcriber: MoshiTranscriber | None = None
synthesizer: MoshiSynthesizer | None = None
player: AudioPlayer | None = None


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


def get_voice_pipeline() -> tuple[AudioRecorder, MoshiTranscriber, MoshiSynthesizer, AudioPlayer]:
    """Get or create voice pipeline instances."""
    global recorder, transcriber, synthesizer, player

    if recorder is None:
        print("Loading voice pipeline (first run downloads ~2GB)...", file=sys.stderr)
        recorder = AudioRecorder()
        transcriber = MoshiTranscriber(hf_repo=config.MOSHI_STT_REPO, quantize=config.MOSHI_QUANTIZE)
        synthesizer = MoshiSynthesizer(voice=config.MOSHI_VOICE, quantize=config.MOSHI_QUANTIZE)
        player = AudioPlayer(config.MOSHI_SAMPLE_RATE)
        print("Voice pipeline ready", file=sys.stderr)

    return recorder, transcriber, synthesizer, player


def handle_start():
    """Handle start command - begin listening (push-to-talk press)."""
    conv = get_or_create_conversation()
    rec, _, _, _ = get_voice_pipeline()

    conv.state = State.LISTENING
    conv.current_transcript = ""

    rec.start()
    print("State: LISTENING", file=sys.stderr)


def handle_stop_and_process():
    """Handle stop_and_process command - stop listening and get response."""
    conv = get_or_create_conversation()
    rec, trans, synth, play = get_voice_pipeline()

    if conv.state != State.LISTENING:
        print("Not listening, nothing to process", file=sys.stderr)
        return

    # Stop recording
    audio = rec.stop()

    if len(audio) == 0:
        print("No audio captured", file=sys.stderr)
        conv.state = State.IDLE
        return

    duration = len(audio) / 24000
    print(f"Captured {duration:.1f}s of audio", file=sys.stderr)

    # Transcribe
    conv.state = State.THINKING
    print("State: THINKING - Transcribing...", file=sys.stderr)

    try:
        transcript = trans.transcribe(audio)
    except Exception as e:
        print(f"Transcription error: {e}", file=sys.stderr)
        conv.state = State.IDLE
        return

    if not transcript:
        print("No speech detected", file=sys.stderr)
        conv.state = State.IDLE
        return

    print(f"You said: {transcript}", file=sys.stderr)
    conv.current_transcript = transcript

    # Get LLM response
    print("Getting response...", file=sys.stderr)
    conv.add_user_message(transcript)
    try:
        response = conv.get_response()
    except Exception as e:
        print(f"LLM error: {e}", file=sys.stderr)
        conv.state = State.IDLE
        return

    conv.add_assistant_message(response)
    print(f"AI: {response}", file=sys.stderr)

    # Synthesize and play
    conv.state = State.SPEAKING
    print("State: SPEAKING", file=sys.stderr)

    try:
        speech = synth.synthesize(response)
        play.play(speech)
    except Exception as e:
        print(f"Speech synthesis error: {e}", file=sys.stderr)

    conv.state = State.IDLE
    print("State: IDLE", file=sys.stderr)


def handle_stop():
    """Handle stop command - cancel and return to idle."""
    global recorder, player
    conv = get_or_create_conversation()

    if recorder and recorder.is_recording:
        recorder.stop()

    if player:
        player.stop()

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
    parser.add_argument("command", choices=["start", "stop_and_process", "stop", "persona"],
                        help="Command to execute")
    parser.add_argument("persona_id", nargs="?", help="Persona ID for persona command")

    args = parser.parse_args()

    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Write PID
    write_pid()

    try:
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
    finally:
        remove_pid()


if __name__ == "__main__":
    main()
