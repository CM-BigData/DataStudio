from __future__ import annotations

from typing import Any

from synthesis_engine.llm import LLMClientConfig, LLMResponse, OpenAIClient


class LLMAccessor:
    def __init__(self, client: Any | None = None, model_config: dict[str, Any] | None = None) -> None:
        """Initialize the LLM access layer

        Business logic:
            1. Prefer a client injected by tests or upper layers
            2. Create an OpenAIClient from model config when no client is provided
            3. Expose a reusable complete boundary for mappers

        Args:
            client (Any | None): Injectable LLM client.
            model_config (dict[str, Any] | None): Model configuration.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> hasattr(LLMAccessor(client=object()), 'complete')
            True
        """
        self.client = client  # LLM client injected for tests or created lazily at runtime.
        self.model_config = model_config or {}  # Model configuration used to build OpenAIClient instances.

    def complete(self, messages: list[dict[str, str]], options: dict[str, Any] | None = None) -> LLMResponse:
        """Call the LLM client

        Business logic:
            1. Use the injected client or create the default OpenAIClient
            2. Forward messages and call options
            3. Return a normalized LLMResponse

        Args:
            messages (list[dict[str, str]]): OpenAI-compatible messages.
            options (dict[str, Any] | None): Call options.

        Returns:
            LLMResponse: Normalized model response.

        Examples:
            >>> callable(LLMAccessor.complete)
            True
        """
        client = self.client or OpenAIClient(LLMClientConfig.from_dict(self.model_config))
        return client.complete(messages, options or {})
