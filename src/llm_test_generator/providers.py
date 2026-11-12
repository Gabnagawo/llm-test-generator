"""LLM providers behind one small interface.

``ollama`` is the default and costs nothing. ``anthropic`` and ``openai`` are optional
extras whose SDKs are imported only when selected. ``fake`` replays scripted answers
and is what the unit tests use.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import httpx

from llm_test_generator.config import Settings
from llm_test_generator.models import ChatMessage, LLMResponse

_THINK_RE = re.compile(r"<think>.*?</think>", flags=re.DOTALL)


class ProviderError(RuntimeError):
    """The provider could not return a completion, even after retries."""


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, messages: Sequence[ChatMessage]) -> LLMResponse: ...

    def options(self) -> dict[str, str | int | float | bool | None]: ...


def strip_thinking(text: str) -> str:
    """Drop ``<think>`` blocks some reasoning models put in the visible content."""
    return _THINK_RE.sub("", text).strip()


class OllamaProvider:
    """Ollama ``/api/chat``. Sampling follows the Qwen3 recommendations, not greedy."""

    name = "ollama"

    def __init__(
        self,
        model: str = "qwen3:8b",
        host: str = "http://localhost:11434",
        *,
        num_ctx: int = 16384,
        think: bool = False,
        presence_penalty: float = 1.5,
        temperature: float | None = None,
        seed: int | None = None,
        timeout_s: float = 300.0,
        retries: int = 4,
        backoff_s: float = 5.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.num_ctx = num_ctx
        self.think = think
        # Qwen3 model card: thinking mode T=0.6/top_p=0.95, non-thinking T=0.7/top_p=0.8,
        # top_k=20 and min_p=0 in both. Greedy decoding makes it loop.
        self.temperature = temperature if temperature is not None else (0.6 if think else 0.7)
        self.top_p = 0.95 if think else 0.8
        # Qwen3 card: presence_penalty in [0, 2] curbs endless repetition in quantized builds
        # (Ollama aborts those with HTTP 500 'token repeat limit reached').
        self.presence_penalty = presence_penalty
        self.seed = seed
        self.retries = retries
        self.backoff_s = backoff_s
        self.client = client or httpx.Client(timeout=timeout_s)

    def options(self) -> dict[str, str | int | float | bool | None]:
        return {
            "host": self.host,
            "num_ctx": self.num_ctx,
            "think": self.think,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": 20,
            "presence_penalty": self.presence_penalty,
            "seed": self.seed,
        }

    def complete(self, messages: Sequence[ChatMessage]) -> LLMResponse:
        start = time.perf_counter()
        last_error = "no attempt made"
        for attempt in range(self.retries + 1):
            options: dict[str, Any] = {
                "num_ctx": self.num_ctx,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": 20,
                "min_p": 0,
                "presence_penalty": self.presence_penalty,
            }
            if self.seed is not None:
                # A retry with the same seed would replay the same bad sample.
                options["seed"] = self.seed + attempt
            payload = {
                "model": self.model,
                "messages": [m.model_dump() for m in messages],
                "stream": False,
                "think": self.think,
                "options": options,
            }
            try:
                resp = self.client.post(f"{self.host}/api/chat", json=payload)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    text = strip_thinking(str(data.get("message", {}).get("content") or ""))
                    if text:
                        return LLMResponse(
                            text=text,
                            provider=self.name,
                            model=self.model,
                            latency_s=round(time.perf_counter() - start, 3),
                            prompt_tokens=data.get("prompt_eval_count"),
                            completion_tokens=data.get("eval_count"),
                            retries=attempt,
                        )
                    last_error = "empty completion"
                elif resp.status_code < 500 and resp.status_code != 429:
                    raise ProviderError(f"ollama HTTP {resp.status_code}: {resp.text[:300]}")
                else:
                    last_error = f"ollama HTTP {resp.status_code}: {resp.text[:300]}"
            if attempt < self.retries:
                # Exponential: a shared server that is busy or reloading needs tens of seconds.
                time.sleep(self.backoff_s * 2**attempt)
        raise ProviderError(f"ollama failed after {self.retries + 1} attempts: {last_error}")


def _split_system(messages: Sequence[ChatMessage]) -> tuple[str, list[dict[str, str]]]:
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    rest = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    return system, rest


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-5-5",
        api_key: str | None = None,
        *,
        timeout_s: float = 300.0,
        retries: int = 2,
        max_tokens: int = 4096,
        client: Any = None,
    ) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on the extra
                raise ProviderError("install the extra: uv sync --extra anthropic") from exc
            client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=retries)
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def options(self) -> dict[str, str | int | float | bool | None]:
        return {"max_tokens": self.max_tokens}

    def complete(self, messages: Sequence[ChatMessage]) -> LLMResponse:
        system, rest = _split_system(messages)
        start = time.perf_counter()
        try:
            msg = self.client.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=system, messages=rest
            )
        except Exception as exc:
            raise ProviderError(f"anthropic: {type(exc).__name__}: {exc}") from exc
        text = "".join(getattr(b, "text", "") for b in msg.content if b.type == "text")
        usage = getattr(msg, "usage", None)
        return LLMResponse(
            text=text.strip(),
            provider=self.name,
            model=self.model,
            latency_s=round(time.perf_counter() - start, 3),
            prompt_tokens=getattr(usage, "input_tokens", None),
            completion_tokens=getattr(usage, "output_tokens", None),
        )


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout_s: float = 300.0,
        retries: int = 2,
        client: Any = None,
    ) -> None:
        if client is None:
            try:
                import openai
            except ImportError as exc:  # pragma: no cover - depends on the extra
                raise ProviderError("install the extra: uv sync --extra openai") from exc
            client = openai.OpenAI(
                api_key=api_key, base_url=base_url, timeout=timeout_s, max_retries=retries
            )
        self.client = client
        self.model = model

    def options(self) -> dict[str, str | int | float | bool | None]:
        return {}

    def complete(self, messages: Sequence[ChatMessage]) -> LLMResponse:
        start = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(
                model=self.model, messages=[m.model_dump() for m in messages]
            )
        except Exception as exc:
            raise ProviderError(f"openai: {type(exc).__name__}: {exc}") from exc
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=strip_thinking(resp.choices[0].message.content or ""),
            provider=self.name,
            model=self.model,
            latency_s=round(time.perf_counter() - start, 3),
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
        )


Script = str | Callable[[Sequence[ChatMessage]], str]


class FakeProvider:
    """Replays scripted completions in order; used by tests and ``--provider fake``."""

    name = "fake"

    def __init__(self, script: Sequence[Script], model: str = "fake") -> None:
        if not script:
            raise ValueError("FakeProvider needs at least one scripted answer")
        self.script = list(script)
        self.model = model
        self.calls: list[list[ChatMessage]] = []

    def options(self) -> dict[str, str | int | float | bool | None]:
        return {"scripted_answers": len(self.script)}

    def complete(self, messages: Sequence[ChatMessage]) -> LLMResponse:
        self.calls.append(list(messages))
        item = self.script[min(len(self.calls), len(self.script)) - 1]
        text = item(messages) if callable(item) else item
        if text.startswith("!error"):
            raise ProviderError(text.removeprefix("!error").strip() or "scripted failure")
        return LLMResponse(text=text, provider=self.name, model=self.model, latency_s=0.0)


def build_provider(settings: Settings, fake_script: Sequence[Script] | None = None) -> LLMProvider:
    """Instantiate the provider selected by ``LLM_PROVIDER`` / ``LLM_MODEL``."""
    model = settings.model
    match settings.llm_provider:
        case "ollama":
            return OllamaProvider(
                model,
                settings.ollama_host,
                num_ctx=settings.ollama_num_ctx,
                think=settings.ollama_think,
                presence_penalty=settings.ollama_presence_penalty,
                temperature=settings.llm_temperature,
                seed=settings.llm_seed,
                timeout_s=settings.llm_timeout_s,
                retries=settings.llm_retries,
            )
        case "anthropic":
            key = settings.anthropic_api_key
            return AnthropicProvider(
                model,
                key.get_secret_value() if key else None,
                timeout_s=settings.llm_timeout_s,
                retries=settings.llm_retries,
            )
        case "openai":
            key = settings.openai_api_key
            return OpenAIProvider(
                model,
                key.get_secret_value() if key else None,
                base_url=settings.openai_base_url,
                timeout_s=settings.llm_timeout_s,
                retries=settings.llm_retries,
            )
        case "fake":
            return FakeProvider(fake_script or ["(no scripted answer)"], model=model)
    raise ValueError(f"unknown provider {settings.llm_provider!r}")  # pragma: no cover
