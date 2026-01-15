"""Tests for LLM router."""

import sys
import pytest
from unittest.mock import patch, MagicMock


# Mock ollama module before importing llm_router
mock_ollama = MagicMock()
sys.modules['ollama'] = mock_ollama


def test_route_to_ollama():
    """Should route to Ollama for local provider."""
    # Re-import to pick up the mock
    import importlib
    if 'llm_router' in sys.modules:
        importlib.reload(sys.modules['llm_router'])
    from llm_router import LLMRouter

    router = LLMRouter()
    llm_config = {"provider": "ollama", "model": "llama3.1:8b"}

    with patch("llm_router.ollama") as mock_ollama:
        mock_ollama.chat.return_value = {"message": {"content": "Hello!"}}

        response = router.chat(
            llm_config=llm_config,
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="You are helpful."
        )

        assert response == "Hello!"
        mock_ollama.chat.assert_called_once()


def test_route_to_redpill():
    """Should route to RedPill for cloud provider."""
    from llm_router import LLMRouter

    router = LLMRouter()
    llm_config = {"provider": "redpill", "model": "z-ai/glm-4.6"}

    with patch("llm_router.httpx") as mock_httpx:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from cloud!"}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_response

        response = router.chat(
            llm_config=llm_config,
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="You are helpful."
        )

        assert response == "Hello from cloud!"


def test_invalid_provider():
    """Should raise error for unknown provider."""
    from llm_router import LLMRouter

    router = LLMRouter()
    llm_config = {"provider": "unknown", "model": "some-model"}

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        router.chat(
            llm_config=llm_config,
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="Test"
        )
