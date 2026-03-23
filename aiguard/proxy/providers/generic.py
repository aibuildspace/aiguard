from __future__ import annotations

from aiguard.config import settings
from aiguard.proxy.providers.base import AbstractProvider


class GenericProvider(AbstractProvider):
    """
    OpenAI-compatible passthrough for any provider using the OAI API format.
    Mounts at /v1/** — useful for tools that send to /v1/chat/completions directly.
    """

    name = "generic"
    base_path = "/v1"

    def extract_content(self, body: dict) -> dict:
        messages = body.get("messages", [])
        system_prompt = None
        system_msgs = [m for m in messages if m.get("role") == "system"]
        if system_msgs:
            system_prompt = " ".join(
                m.get("content", "") for m in system_msgs if isinstance(m.get("content"), str)
            )
        chat_messages = [m for m in messages if m.get("role") != "system"]
        return {
            "messages": chat_messages,
            "system_prompt": system_prompt,
            "tool_results": [],
            "model": body.get("model", ""),
        }

    def upstream_url(self, path: str) -> str:
        # Default to OpenAI; caller can override via GUARD_OPENAI_BASE_URL
        base = settings.openai_base_url.rstrip("/")
        return f"{base}{path}"

    def strip_path_prefix(self, path: str) -> str:
        return path

    def extract_token_counts(self, response_body: dict) -> tuple[int | None, int | None]:
        usage = response_body.get("usage", {})
        return usage.get("prompt_tokens"), usage.get("completion_tokens")
