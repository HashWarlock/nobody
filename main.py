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


def handle_start():
    """Handle start command - begin listening (push-to-talk press)."""
    conv = get_or_create_conversation()
    conv.state = State.LISTENING
    conv.current_transcript = ""
    print("State: LISTENING", file=sys.stderr)
    print("Listening...", file=sys.stderr)
    # TODO: Start STT with Kyutai


def handle_stop_and_process():
    """Handle stop_and_process command - stop listening and get response (push-to-talk release)."""
    conv = get_or_create_conversation()

    if conv.state != State.LISTENING:
        print("Not listening, nothing to process", file=sys.stderr)
        return

    conv.state = State.THINKING
    print("State: THINKING", file=sys.stderr)
    print("Processing...", file=sys.stderr)

    # TODO: Get transcript from STT
    # For now, use placeholder if no transcript
    if not conv.current_transcript:
        conv.current_transcript = "[No audio captured - STT not yet integrated]"

    # Process the transcript
    conv.add_user_message(conv.current_transcript)
    response = conv.get_response()
    conv.add_assistant_message(response)
    print(f"Response: {response}", file=sys.stderr)

    # TODO: Start TTS with Kyutai
    conv.state = State.IDLE


def handle_stop():
    """Handle stop command - cancel and return to idle."""
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
