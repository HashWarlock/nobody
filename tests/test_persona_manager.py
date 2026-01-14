"""Tests for persona manager."""

import pytest
from pathlib import Path


def test_load_personas_from_yaml():
    """Should load all personas from YAML file."""
    from persona_manager import PersonaManager

    manager = PersonaManager()

    assert "assistant" in manager.personas
    assert "tutor" in manager.personas
    assert "creative" in manager.personas
    assert "casual" in manager.personas


def test_get_default_persona():
    """Should return the default persona on init."""
    from persona_manager import PersonaManager

    manager = PersonaManager()
    persona = manager.get_current()

    assert persona["name"] == "Assistant"
    assert persona["llm"]["provider"] == "ollama"


def test_switch_persona():
    """Should switch to a different persona."""
    from persona_manager import PersonaManager

    manager = PersonaManager()
    manager.switch("tutor")
    persona = manager.get_current()

    assert persona["name"] == "Tutor"
    assert persona["llm"]["provider"] == "redpill"
    assert persona["llm"]["model"] == "z-ai/glm-4.6"


def test_switch_invalid_persona():
    """Should raise error for invalid persona."""
    from persona_manager import PersonaManager

    manager = PersonaManager()

    with pytest.raises(ValueError, match="Unknown persona"):
        manager.switch("nonexistent")
