"""Settings from environment variables (and an optional ``.env`` file)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["ollama", "anthropic", "openai", "fake"]

DEFAULT_MODELS: dict[str, str] = {
    "ollama": "qwen3:8b",
    "anthropic": "claude-sonnet-5-5",
    "fake": "fake",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    llm_provider: ProviderName = Field(default="ollama", alias="LLM_PROVIDER")
    llm_model: str | None = Field(default=None, alias="LLM_MODEL")
    llm_timeout_s: float = Field(default=300.0, gt=0, alias="LLM_TIMEOUT_S")
    llm_retries: int = Field(default=2, ge=0, le=10, alias="LLM_RETRIES")
    llm_temperature: float | None = Field(default=None, ge=0, le=2, alias="LLM_TEMPERATURE")
    llm_seed: int | None = Field(default=None, alias="LLM_SEED")

    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    # qwen3 needs room for the catalog, the story, the previous attempt and its error.
    # Keep the same value as other clients of a shared server: a different num_ctx
    # makes Ollama reload the model.
    ollama_num_ctx: int = Field(default=16384, ge=2048, alias="OLLAMA_NUM_CTX")
    ollama_think: bool = Field(default=False, alias="OLLAMA_THINK")
    ollama_presence_penalty: float = Field(default=1.5, ge=0, le=2, alias="OLLAMA_PRESENCE_PENALTY")

    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")

    base_url: str = Field(default="https://www.saucedemo.com", alias="LTG_BASE_URL")
    max_repairs: int = Field(default=2, ge=0, le=5, alias="LTG_MAX_REPAIRS")
    test_timeout_s: float = Field(default=120.0, gt=0, alias="LTG_TEST_TIMEOUT_S")

    @property
    def model(self) -> str:
        if self.llm_model:
            return self.llm_model
        if self.llm_provider == "openai":
            raise ValueError("LLM_PROVIDER=openai needs LLM_MODEL (no default model is assumed)")
        return DEFAULT_MODELS[self.llm_provider]
