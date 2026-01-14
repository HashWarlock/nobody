"""Tests for conversation state machine."""

import sys
import pytest
from unittest.mock import MagicMock, patch

# Mock ollama module before importing conversation (which imports llm_router)
mock_ollama = MagicMock()
sys.modules['ollama'] = mock_ollama


def test_initial_state_is_idle():
    """Conversation should start in IDLE state."""
    from conversation import Conversation, State

    conv = Conversation(persona_manager=MagicMock(), llm_router=MagicMock())

    assert conv.state == State.IDLE


def test_toggle_from_idle_starts_listening():
    """Toggle from IDLE should transition to LISTENING."""
    from conversation import Conversation, State

    conv = Conversation(persona_manager=MagicMock(), llm_router=MagicMock())
    conv.toggle()

    assert conv.state == State.LISTENING


def test_toggle_from_listening_starts_thinking():
    """Toggle from LISTENING should transition to THINKING."""
    from conversation import Conversation, State

    mock_persona = MagicMock()
    mock_persona.get_current.return_value = {
        "llm": {"provider": "ollama", "model": "test"},
        "system_prompt": "test"
    }

    conv = Conversation(persona_manager=mock_persona, llm_router=MagicMock())
    conv.state = State.LISTENING
    conv.current_transcript = "Hello"
    conv.toggle()

    assert conv.state == State.THINKING


def test_stop_returns_to_idle():
    """Stop from any state should return to IDLE."""
    from conversation import Conversation, State

    conv = Conversation(persona_manager=MagicMock(), llm_router=MagicMock())

    for state in [State.LISTENING, State.THINKING, State.SPEAKING]:
        conv.state = state
        conv.stop()
        assert conv.state == State.IDLE


def test_message_history_maintained():
    """Conversation should maintain message history."""
    from conversation import Conversation, State

    conv = Conversation(persona_manager=MagicMock(), llm_router=MagicMock())

    conv.add_user_message("Hello")
    conv.add_assistant_message("Hi there!")

    assert len(conv.messages) == 2
    assert conv.messages[0] == {"role": "user", "content": "Hello"}
    assert conv.messages[1] == {"role": "assistant", "content": "Hi there!"}
