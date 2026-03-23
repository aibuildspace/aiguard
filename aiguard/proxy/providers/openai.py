from __future__ import annotations

from aiguard.config import settings
from aiguard.proxy.providers.base import AbstractProvider


class OpenAIProvider(AbstractProvider):
    name = "openai"
    base_path = "/openai"

    def extract_content(self, body: dict) -> dict:
        # ----- Chat Completions format (body.messages) -----
        messages = body.get("messages", [])

        # ----- Responses API format (body.input) -----
        # The Responses API uses "input" which can be a string or a list
        # of message-like items.  Normalize them into the same messages
        # list so shields see the content.
        resp_input = body.get("input")
        if resp_input is not None and not messages:
            messages = self._normalize_responses_input(resp_input)

        # Extract system prompt (OpenAI uses role="system" or "developer" messages)
        system_prompt: str | None = None
        system_msgs = [
            m for m in messages
            if m.get("role") in ("system", "developer")
        ]
        if system_msgs:
            system_prompt = " ".join(
                m.get("content", "") if isinstance(m.get("content"), str) else ""
                for m in system_msgs
            )

        # Non-system messages become the messages list
        chat_messages = [
            m for m in messages
            if m.get("role") not in ("system", "developer")
        ]

        # Tool results are "tool" role messages
        tool_results = [
            {"content": m.get("content", "")}
            for m in messages
            if m.get("role") == "tool"
        ]

        return {
            "messages": chat_messages,
            "system_prompt": system_prompt,
            "tool_results": tool_results,
            "model": body.get("model", ""),
        }

    # ------------------------------------------------------------------
    # Responses API input normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_responses_input(inp: str | list | dict) -> list[dict]:
        """
        Convert the ``input`` field of an OpenAI Responses API request
        into a list of ``{"role": ..., "content": ...}`` dicts that the
        shield scanner understands.

        ``input`` may be:
        • a plain string  →  single user message
        • a list of message objects (role + content)
        • a list of mixed content-part items
        """
        if isinstance(inp, str):
            return [{"role": "user", "content": inp}]

        if not isinstance(inp, list):
            return []

        messages: list[dict] = []
        for item in inp:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
                continue
            if not isinstance(item, dict):
                continue

            role = item.get("role", "user")
            content = item.get("content", "")

            # Responses API content can be a list of typed parts
            if isinstance(content, list):
                text_parts: list[str] = []
                for part in content:
                    if isinstance(part, dict):
                        # input_text parts
                        if part.get("type") == "input_text":
                            text_parts.append(part.get("text", ""))
                        # text parts
                        elif part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        # message-type items (nested)
                        elif part.get("type") == "message":
                            inner_role = part.get("role", role)
                            inner_content = part.get("content", "")
                            if isinstance(inner_content, list):
                                inner_text = " ".join(
                                    p.get("text", "")
                                    for p in inner_content
                                    if isinstance(p, dict) and p.get("type") in ("input_text", "text", "output_text")
                                )
                            elif isinstance(inner_content, str):
                                inner_text = inner_content
                            else:
                                inner_text = ""
                            if inner_text:
                                messages.append({"role": inner_role, "content": inner_text})
                    elif isinstance(part, str):
                        text_parts.append(part)
                if text_parts:
                    messages.append({"role": role, "content": " ".join(text_parts)})
            elif isinstance(content, str) and content:
                messages.append({"role": role, "content": content})
            # Items without content but with "type" (e.g. function_call_output)
            elif item.get("type") == "function_call_output":
                output = item.get("output", "")
                if output:
                    messages.append({"role": "tool", "content": output})

        return messages

    def upstream_url(self, path: str) -> str:
        stripped = self.strip_path_prefix(path)
        base = settings.openai_base_url.rstrip("/")
        return f"{base}{stripped}"

    def strip_path_prefix(self, path: str) -> str:
        if path.startswith(self.base_path):
            return path[len(self.base_path):]
        return path

    def extract_token_counts(self, response_body: dict) -> tuple[int | None, int | None]:
        usage = response_body.get("usage", {})
        # Chat Completions format
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        # Responses API format
        if input_tokens is None:
            input_tokens = usage.get("input_tokens")
        if output_tokens is None:
            output_tokens = usage.get("output_tokens")
        return input_tokens, output_tokens
