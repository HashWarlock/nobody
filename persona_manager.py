"""Persona manager for loading and switching between conversation personas."""

import yaml
from pathlib import Path
from typing import Any

import config


class PersonaManager:
    """Manages persona loading and switching."""

    def __init__(self, personas_file: Path | None = None):
        """Load personas from YAML file.

        Args:
            personas_file: Path to personas YAML. Defaults to config.PERSONAS_FILE.
        """
        self.personas_file = personas_file or config.PERSONAS_FILE
        self._load_personas()
        self.current_persona_id = self.default_persona

    def _load_personas(self) -> None:
        """Load personas from YAML file."""
        with open(self.personas_file) as f:
            data = yaml.safe_load(f)

        self.default_persona = data.get("default_persona", "assistant")
        self.personas = data.get("personas", {})

    def get_current(self) -> dict[str, Any]:
        """Get the currently active persona configuration.

        Returns:
            Persona configuration dict with name, llm, voice, system_prompt.
        """
        return self.personas[self.current_persona_id]

    def switch(self, persona_id: str) -> dict[str, Any]:
        """Switch to a different persona.

        Args:
            persona_id: ID of persona to switch to (e.g., "tutor", "creative").

        Returns:
            The new persona configuration.

        Raises:
            ValueError: If persona_id is not found.
        """
        if persona_id not in self.personas:
            raise ValueError(f"Unknown persona: {persona_id}")

        self.current_persona_id = persona_id
        return self.get_current()

    def list_personas(self) -> list[str]:
        """List all available persona IDs.

        Returns:
            List of persona ID strings.
        """
        return list(self.personas.keys())
