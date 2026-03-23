from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AbstractProvider(ABC):
    """
    Contract for provider-specific request parsing and response handling.

    Each provider (Anthropic, OpenAI, generic) implements this interface so
    the proxy core can work with normalized content regardless of the upstream
    API's wire format.
    """

    name: str  # e.g. "anthropic", "openai"
    base_path: str  # URL prefix this provider handles, e.g. "/anthropic"

    @abstractmethod
    def extract_content(self, body: dict) -> dict:
        """
        Parse the raw request body and return a normalized content dict:
        {
            "messages": [{"role": str, "content": str | list}],
            "system_prompt": str | None,
            "tool_results": [{"content": str | list}],
            "model": str,
        }
        """

    @abstractmethod
    def upstream_url(self, path: str) -> str:
        """
        Build the full upstream URL for the given request path.
        e.g. "/anthropic/v1/messages" → "https://api.anthropic.com/v1/messages"
        """

    @abstractmethod
    def strip_path_prefix(self, path: str) -> str:
        """
        Remove the provider's routing prefix from the path.
        e.g. "/anthropic/v1/messages" → "/v1/messages"
        """

    def extract_token_counts(self, response_body: dict) -> tuple[int | None, int | None]:
        """
        Extract (input_tokens, output_tokens) from the upstream response body.
        Returns (None, None) if not available.
        """
        return None, None
