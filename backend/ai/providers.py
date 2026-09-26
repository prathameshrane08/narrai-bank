"""Pluggable LLM providers.

Banks differ in where model inference may run, so the narrator talks to a small
interface instead of a specific vendor:

- ``ollama`` (default): a local model; customer data never leaves the machine.
- ``openai_compatible``: any server that speaks the OpenAI chat-completions API,
  e.g. a bank's own vLLM deployment or an EU-hosted model provider.

Configure with NARRAI_LLM_PROVIDER, NARRAI_MODEL, NARRAI_LLM_BASE_URL,
NARRAI_LLM_API_KEY and NARRAI_LLM_TIMEOUT.
"""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol


class LLMProvider(Protocol):
    name: str
    model: str

    def complete_json(self, prompt: str) -> dict:
        """Send one user prompt and return the model's reply parsed as a JSON object."""
        ...


def _parse_json_object(content: str) -> dict:
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM reply was JSON but not an object")
    return parsed


@dataclass
class OllamaProvider:
    model: str
    host: str
    timeout: float
    temperature: float = 0.2
    name: str = "ollama"

    def complete_json(self, prompt: str) -> dict:
        import ollama

        client = ollama.Client(host=self.host, timeout=self.timeout)
        response = client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={"temperature": self.temperature},
        )
        return _parse_json_object(response["message"]["content"])


@dataclass
class OpenAICompatibleProvider:
    model: str
    base_url: str
    api_key: str
    timeout: float
    temperature: float = 0.2
    name: str = "openai_compatible"

    def complete_json(self, prompt: str) -> dict:
        from openai import OpenAI

        client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=self.temperature,
        )
        return _parse_json_object(response.choices[0].message.content or "")


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    provider = os.getenv("NARRAI_LLM_PROVIDER", "ollama")
    timeout = float(os.getenv("NARRAI_LLM_TIMEOUT", os.getenv("NARRAI_OLLAMA_TIMEOUT", "120")))

    if provider == "ollama":
        return OllamaProvider(
            model=os.getenv("NARRAI_MODEL", "llama3.2:3b"),
            host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
            timeout=timeout,
        )

    if provider == "openai_compatible":
        base_url = os.getenv("NARRAI_LLM_BASE_URL")
        model = os.getenv("NARRAI_MODEL")
        if not base_url or not model:
            raise RuntimeError("openai_compatible provider needs NARRAI_LLM_BASE_URL and NARRAI_MODEL")
        return OpenAICompatibleProvider(
            model=model,
            base_url=base_url,
            api_key=os.getenv("NARRAI_LLM_API_KEY", "not-needed"),
            timeout=timeout,
        )

    raise RuntimeError(f"Unknown NARRAI_LLM_PROVIDER '{provider}' (use 'ollama' or 'openai_compatible')")
