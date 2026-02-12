"""LLM router for directing requests to Ollama or RedPill."""

import json
import sys
from typing import Any, Callable

import httpx
import ollama

import config


class LLMRouter:
    """Routes LLM requests to appropriate provider."""

    MAX_TOOL_ROUNDS = 10  # Safety limit on tool call loops

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

    def chat_with_tools(
        self,
        llm_config: dict[str, str],
        messages: list[dict[str, str]],
        system_prompt: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], str],
    ) -> str:
        """Send chat request with tool calling support.

        Loops until the LLM produces a final text response:
        1. Call LLM with messages + tools
        2. If response has tool_calls → execute each, append results, goto 1
        3. If response is text → return it

        Args:
            llm_config: Dict with 'provider' and 'model' keys.
            messages: Conversation message history.
            system_prompt: System prompt for the conversation.
            tools: OpenAI-format tool definitions.
            tool_executor: Function(name, arguments) -> result string.

        Returns:
            Final assistant response text.
        """
        provider = llm_config["provider"]
        model = llm_config["model"]

        if provider != "redpill":
            # Tool calling only supported via OpenAI-compatible API
            return self.chat(llm_config, messages, system_prompt)

        # Build working message list (includes tool call/result messages during loop)
        working_messages = [{"role": "system", "content": system_prompt}] + list(messages)

        for round_num in range(self.MAX_TOOL_ROUNDS):
            print(f"LLM call (round {round_num + 1}), model={model}...", file=sys.stderr)

            try:
                response = httpx.post(
                    f"{self.redpill_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.redpill_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": working_messages,
                        "tools": tools,
                    },
                    timeout=self.timeout,
                )
                print(f"  HTTP {response.status_code}", file=sys.stderr)
                response.raise_for_status()
                result = response.json()
            except httpx.HTTPStatusError as e:
                print(f"  API error: {e.response.status_code} {e.response.text[:500]}", file=sys.stderr)
                raise
            except httpx.RequestError as e:
                print(f"  Request error: {e}", file=sys.stderr)
                raise

            choice = result["choices"][0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason", "stop")

            # Check for tool calls
            tool_calls = message.get("tool_calls")

            if not tool_calls or finish_reason == "stop":
                # No tool calls — return the text response
                return message.get("content", "")

            # Append the assistant message with tool calls to working messages
            working_messages.append(message)

            # Execute each tool call and append results
            for tc in tool_calls:
                func = tc["function"]
                tool_name = func["name"]
                try:
                    tool_args = json.loads(func["arguments"]) if isinstance(func["arguments"], str) else func["arguments"]
                except (json.JSONDecodeError, TypeError):
                    tool_args = {}

                print(f"  Tool: {tool_name}({tool_args})", file=sys.stderr)
                tool_result = tool_executor(tool_name, tool_args)
                print(f"  Result: {tool_result[:100]}{'...' if len(tool_result) > 100 else ''}", file=sys.stderr)

                working_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

        # Safety: exceeded max rounds
        return message.get("content", "I had trouble completing that request. Could you try again?")

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
