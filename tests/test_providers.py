from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from llm_test_generator.config import Settings
from llm_test_generator.models import ChatMessage
from llm_test_generator.providers import (
    AnthropicProvider,
    FakeProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderError,
    build_provider,
    strip_thinking,
)

MESSAGES = [
    ChatMessage(role="system", content="be brief"),
    ChatMessage(role="user", content="hi"),
]


def ollama_with(responses: list[httpx.Response | Exception], **kwargs: Any):
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        item = responses[min(len(requests), len(responses)) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(client=client, backoff_s=0, **kwargs)
    return provider, requests


def ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"message": {"content": content}, "prompt_eval_count": 11, "eval_count": 7},
    )


def test_ollama_success_sends_context_and_sampling() -> None:
    provider, requests = ollama_with([ok("<think>hmm</think>answer")], seed=7)
    resp = provider.complete(MESSAGES)
    assert (resp.text, resp.prompt_tokens, resp.completion_tokens, resp.retries) == (
        "answer",
        11,
        7,
        0,
    )
    sent = requests[0]
    assert sent["think"] is False
    assert sent["stream"] is False
    assert sent["options"] == {
        "num_ctx": 16384,
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0,
        "seed": 7,
    }
    assert sent["messages"][0] == {"role": "system", "content": "be brief"}


def test_ollama_thinking_mode_sampling() -> None:
    provider, _ = ollama_with([ok("x")], think=True)
    assert provider.options()["temperature"] == 0.6
    assert provider.options()["top_p"] == 0.95


def test_ollama_retries_5xx_transport_errors_and_empty_answers_with_new_seed() -> None:
    provider, requests = ollama_with(
        [
            httpx.Response(500, text="model runner crashed"),
            httpx.ConnectError("refused"),
            ok("   "),
            ok("finally"),
        ],
        retries=3,
        seed=1,
    )
    resp = provider.complete(MESSAGES)
    assert resp.text == "finally"
    assert resp.retries == 3
    assert [r["options"]["seed"] for r in requests] == [1, 2, 3, 4]


def test_ollama_gives_up_after_retries() -> None:
    provider, requests = ollama_with([httpx.Response(503, text="busy")], retries=1)
    with pytest.raises(ProviderError, match="after 2 attempts: ollama HTTP 503"):
        provider.complete(MESSAGES)
    assert len(requests) == 2


def test_ollama_client_errors_are_not_retried() -> None:
    provider, requests = ollama_with([httpx.Response(404, text="model not found")])
    with pytest.raises(ProviderError, match="HTTP 404"):
        provider.complete(MESSAGES)
    assert len(requests) == 1


def test_strip_thinking() -> None:
    assert strip_thinking("<think>\na\n</think>\n\n```python\nx\n```") == "```python\nx\n```"


class FakeAnthropicClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.kwargs: dict[str, Any] = {}
        self.messages = self

    def create(self, **kwargs: Any) -> Any:
        if self.fail:
            raise RuntimeError("overloaded")
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=" code "), SimpleNamespace(type="tool_use")],
            usage=SimpleNamespace(input_tokens=5, output_tokens=3),
        )


def test_anthropic_provider_splits_system_prompt() -> None:
    client = FakeAnthropicClient()
    provider = AnthropicProvider(client=client)
    resp = provider.complete(MESSAGES)
    assert (resp.text, resp.model, resp.prompt_tokens) == ("code", "claude-sonnet-5-5", 5)
    assert client.kwargs["system"] == "be brief"
    assert client.kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert provider.options() == {"max_tokens": 4096}
    with pytest.raises(ProviderError, match="overloaded"):
        AnthropicProvider(client=FakeAnthropicClient(fail=True)).complete(MESSAGES)


class FakeOpenAIClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:
        if self.fail:
            raise RuntimeError("rate limited")
        message = SimpleNamespace(content="<think>x</think>done")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=9, completion_tokens=2),
        )


def test_openai_provider() -> None:
    provider = OpenAIProvider("gpt-test", client=FakeOpenAIClient())
    resp = provider.complete(MESSAGES)
    assert (resp.text, resp.model, resp.completion_tokens) == ("done", "gpt-test", 2)
    assert provider.options() == {}
    with pytest.raises(ProviderError, match="rate limited"):
        OpenAIProvider("m", client=FakeOpenAIClient(fail=True)).complete(MESSAGES)


def test_fake_provider_replays_and_repeats_last_answer() -> None:
    provider = FakeProvider(["one", lambda msgs: f"two:{len(msgs)}", "!error boom"])
    assert provider.complete(MESSAGES).text == "one"
    assert provider.complete(MESSAGES).text == "two:2"
    with pytest.raises(ProviderError, match="boom"):
        provider.complete(MESSAGES)
    with pytest.raises(ProviderError):
        provider.complete(MESSAGES)
    assert len(provider.calls) == 4
    with pytest.raises(ValueError, match="at least one"):
        FakeProvider([])


def settings(**env: Any) -> Settings:
    return Settings.model_validate(env)


def test_build_provider_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    ollama = build_provider(settings(LLM_PROVIDER="ollama", OLLAMA_NUM_CTX=8192, LLM_SEED=3))
    assert isinstance(ollama, OllamaProvider)
    assert (ollama.model, ollama.num_ctx, ollama.seed) == ("qwen3:8b", 8192, 3)
    fake = build_provider(settings(LLM_PROVIDER="fake"), fake_script=["x"])
    assert isinstance(fake, FakeProvider)
    assert fake.model == "fake"


def test_openai_needs_an_explicit_model() -> None:
    with pytest.raises(ValueError, match="needs LLM_MODEL"):
        build_provider(settings(LLM_PROVIDER="openai"))


def test_hosted_providers_receive_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class Recorder:
        def __init__(self, model: str, api_key: str | None, **kwargs: Any) -> None:
            captured[model] = api_key

    monkeypatch.setattr("llm_test_generator.providers.AnthropicProvider", Recorder)
    monkeypatch.setattr("llm_test_generator.providers.OpenAIProvider", Recorder)
    build_provider(settings(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-a"))
    build_provider(settings(LLM_PROVIDER="openai", LLM_MODEL="gpt-x", OPENAI_API_KEY="sk-o"))
    build_provider(settings(LLM_PROVIDER="openai", LLM_MODEL="no-key"))
    assert captured == {"claude-sonnet-5-5": "sk-a", "gpt-x": "sk-o", "no-key": None}
