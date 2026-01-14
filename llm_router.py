"""LLM router for directing requests to Ollama or RedPill."""

from typing import Any

import httpx
import ollama

import config


class LLMRouter:
    """Routes LLM requests to appropriate provider."""

    def __init__(self):
        """Initialize router with API configurations."""
        self.redpill_api_key = config.REDPILL_API_KEY
        self.redpill_base_url = config.REDPILL_BASE_URL
        self.ollama_host = config.OLLAMA_HOST
        self.timeout = config.LLM_TIMEOUT_SEC

    def chat(
        self,
        llm_config: dict[str, str],
        messages: list[dict[str, str]],
        system_prompt: str
    ) -> str:
        """Send chat request to appropriate LLM provider.

        Args:
            llm_config: Dict with 'provider' and 'model' keys.
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: System prompt for the conversation.

        Returns:
            The assistant's response text.

        Raises:
            ValueError: If provider is unknown.
        """
        provider = llm_config["provider"]
        model = llm_config["model"]

        if provider == "ollama":
            return self._chat_ollama(model, messages, system_prompt)
        elif provider == "redpill":
            return self._chat_redpill(model, messages, system_prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _chat_ollama(
        self,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str
    ) -> str:
        """Send request to local Ollama instance."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        response = ollama.chat(
            model=model,
            messages=full_messages
        )

        return response["message"]["content"]

    def _chat_redpill(
        self,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str
    ) -> str:
        """Send request to RedPill API."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        response = httpx.post(
            f"{self.redpill_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.redpill_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": full_messages
            },
            timeout=self.timeout
        )
        response.raise_for_status()

        return response.json()["choices"][0]["message"]["content"]
