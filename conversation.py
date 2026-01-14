"""Conversation state machine for managing voice interaction flow."""

from enum import Enum, auto
from typing import Any

from persona_manager import PersonaManager
from llm_router import LLMRouter


class State(Enum):
    """Conversation states."""
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()


class Conversation:
    """Manages conversation state and message history."""

    MAX_HISTORY = 10  # Keep last N turn pairs

    def __init__(self, persona_manager: PersonaManager, llm_router: LLMRouter):
        """Initialize conversation.

        Args:
            persona_manager: Manager for persona configuration.
            llm_router: Router for LLM requests.
        """
        self.persona_manager = persona_manager
        self.llm_router = llm_router
        self.state = State.IDLE
        self.messages: list[dict[str, str]] = []
        self.current_transcript = ""

    def toggle(self) -> State:
        """Toggle conversation state.

        IDLE -> LISTENING
        LISTENING -> THINKING (if transcript exists)

        Returns:
            New state after toggle.
        """
        if self.state == State.IDLE:
            self.state = State.LISTENING
            self.current_transcript = ""
        elif self.state == State.LISTENING:
            if self.current_transcript:
                self.state = State.THINKING

        return self.state

    def stop(self) -> State:
        """Stop conversation and return to idle.

        Returns:
            IDLE state.
        """
        self.state = State.IDLE
        self.current_transcript = ""
        return self.state

    def add_user_message(self, content: str) -> None:
        """Add user message to history.

        Args:
            content: The user's message text.
        """
        self.messages.append({"role": "user", "content": content})
        self._trim_history()

    def add_assistant_message(self, content: str) -> None:
        """Add assistant message to history.

        Args:
            content: The assistant's response text.
        """
        self.messages.append({"role": "assistant", "content": content})
        self._trim_history()

    def _trim_history(self) -> None:
        """Trim message history to MAX_HISTORY turn pairs."""
        max_messages = self.MAX_HISTORY * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    def get_response(self) -> str:
        """Get LLM response for current conversation.

        Returns:
            Assistant response text.
        """
        persona = self.persona_manager.get_current()

        response = self.llm_router.chat(
            llm_config=persona["llm"],
            messages=self.messages,
            system_prompt=persona["system_prompt"]
        )

        return response

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.messages = []
