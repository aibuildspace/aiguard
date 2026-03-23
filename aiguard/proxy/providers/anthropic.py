from __future__ import annotations

from typing import Any

from aiguard.config import settings
from aiguard.proxy.providers.base import AbstractProvider


class AnthropicProvider(AbstractProvider):
    name = "anthropic"
    base_path = "/anthropic"

    def extract_content(self, body: dict) -> dict:
        messages = body.get("messages", [])
        system = body.get("system")

        # Normalize system: can be a string or a list of content blocks
        system_prompt: str | None = None
        if isinstance(system, str):
            system_prompt = system
        elif isinstance(system, list):
            parts = [
                b.get("text", "")
                for b in system
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            system_prompt = " ".join(parts)

        # Extract tool_use results from messages
        tool_results = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append({"content": block.get("content", "")})

        return {
            "messages": messages,
            "system_prompt": system_prompt,
            "tool_results": tool_results,
            "model": body.get("model", ""),
        }

    def upstream_url(self, path: str) -> str:
        stripped = self.strip_path_prefix(path)
        base = settings.anthropic_base_url.rstrip("/")
        return f"{base}{stripped}"

    def strip_path_prefix(self, path: str) -> str:
        if path.startswith(self.base_path):
            return path[len(self.base_path):]
        return path

    def extract_token_counts(self, response_body: dict) -> tuple[int | None, int | None]:
        usage = response_body.get("usage", {})
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        return input_tokens, output_tokens
