"""Single shared entry point for every AI module to talk to an LLM.

Centralizing this means: one place to swap providers, one place to add
caching/retries, and one place to disable AI features entirely (tests that
import a specific ai/* module still work — they just raise a clear error if
called without an API key, instead of failing deep inside a helper).
"""
from __future__ import annotations

import base64
import json
from typing import Any

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings


def strip_code_fences(raw: str) -> str:
    """Remove a surrounding ```json ... ``` / ``` ... ``` fence if the model added one."""
    return raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


class LLMClient:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or settings.llm_model
        api_key = api_key or settings.anthropic_api_key
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. AI-assisted features require it — "
                "set it in .env or disable the relevant AI_*_ENABLED flag."
            )
        self._client = Anthropic(api_key=api_key)

    def _complete(self, prompt: str, system: str | None, max_tokens: int) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def ask(self, prompt: str, system: str | None = None, max_tokens: int = 1024) -> str:
        return self._complete(prompt, system, max_tokens)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def ask_json(self, prompt: str, system: str | None = None, max_tokens: int = 1536) -> Any:
        """Ask the model for structured JSON output and parse it.

        Appends an explicit "respond with JSON only" instruction rather than
        relying on a provider-specific structured-output mode, so this keeps
        working if the model/provider is swapped out later.

        Calls the un-retried `_complete` so a malformed-JSON response re-asks
        the model (this decorator), without multiplying against `ask`'s own
        retry loop.
        """
        json_system = (system or "") + (
            "\n\nRespond with ONLY valid JSON. No prose, no markdown code fences."
        )
        raw = self._complete(prompt, system=json_system, max_tokens=max_tokens)
        return json.loads(strip_code_fences(raw))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def ask_with_image(self, prompt: str, image_bytes: bytes, media_type: str = "image/png",
                        system: str | None = None, max_tokens: int = 1024) -> str:
        """Vision call — used by visual_ai.py and self_healing.py to reason over screenshots."""
        b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")
        content: list[Any] = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_image}},
            {"type": "text", "text": prompt},
        ]
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system or "",
            messages=[{"role": "user", "content": content}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


_default_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Lazy singleton so importing ai/* modules never requires an API key up front."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
