from aigate.proxy.providers.anthropic import AnthropicProvider
from aigate.proxy.providers.generic import GenericProvider
from aigate.proxy.providers.openai import OpenAIProvider

PROVIDERS = [AnthropicProvider(), OpenAIProvider(), GenericProvider()]
PROVIDER_MAP = {p.name: p for p in PROVIDERS}

__all__ = ["AnthropicProvider", "GenericProvider", "OpenAIProvider", "PROVIDERS", "PROVIDER_MAP"]
