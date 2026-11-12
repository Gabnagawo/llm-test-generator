"""Pydantic models shared across the pipeline.

Everything written to the attempt log (``attempts.json``) is defined here, so the
log has one schema and can be reloaded by ``ltg report``.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ATTEMPT_LOG_SCHEMA_VERSION = 1


class StoryFormat(StrEnum):
    MARKDOWN = "markdown"
    GHERKIN = "gherkin"


class Story(BaseModel):
    """One testable unit: a Markdown user story or a single Gherkin scenario."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Filesystem-safe slug, unique within a run.")
    title: str
    narrative: str = ""
    criteria: list[str] = Field(min_length=1)
    source: str = Field(description="File the story was parsed from.")
    format: StoryFormat
    tags: list[str] = Field(default_factory=list)

    @property
    def test_name(self) -> str:
        """Name of the pytest function the LLM is asked to write."""
        return "test_" + re.sub(r"[^0-9a-zA-Z]+", "_", self.id).strip("_").lower()

    @property
    def test_filename(self) -> str:
        return f"{self.test_name}.py"

    @property
    def text(self) -> str:
        """All human-written text of the story, used for keyword matching."""
        return "\n".join([self.title, self.narrative, *self.criteria])


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    """Normalised completion returned by every provider."""

    text: str
    provider: str
    model: str
    latency_s: float = Field(description="Wall-clock seconds for the call, retries included.")
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    retries: int = Field(default=0, description="Transport-level retries that were needed.")


class FailureCategory(StrEnum):
    """Why an attempt did not produce a passing test."""

    # LLM / transport
    PROVIDER_ERROR = "provider_error"
    NO_CODE = "no_code"
    # static validation
    SYNTAX_ERROR = "syntax_error"
    STRUCTURE_ERROR = "structure_error"
    FORBIDDEN_CONSTRUCT = "forbidden_construct"
    UNKNOWN_SELECTOR = "unknown_selector"
    LINT_ERROR = "lint_error"
    # execution
    COLLECTION_ERROR = "collection_error"
    LOCATOR_TIMEOUT = "locator_timeout"
    STRICT_MODE_VIOLATION = "strict_mode_violation"
    ASSERTION_FAILED = "assertion_failed"
    PYTHON_ERROR = "python_error"
    NAVIGATION_ERROR = "navigation_error"
    EXECUTION_TIMEOUT = "execution_timeout"
    NO_TESTS_RAN = "no_tests_ran"
    OTHER = "other"


class Issue(BaseModel):
    """One static-validation finding."""

    rule: str
    message: str
    category: FailureCategory
    line: int | None = None

    def render(self) -> str:
        where = f"line {self.line}: " if self.line else ""
        return f"[{self.rule}] {where}{self.message}"


class ValidationReport(BaseModel):
    """Outcome of static validation; ``code`` is the normalised source that was checked."""

    code: str
    issues: list[Issue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def primary_category(self) -> FailureCategory | None:
        return self.issues[0].category if self.issues else None


class ExecutionStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"
    NO_TESTS = "no_tests"


class ExecutionResult(BaseModel):
    """Outcome of running one generated test file with pytest."""

    status: ExecutionStatus
    duration_s: float
    exit_code: int | None = None
    tests_total: int = 0
    tests_passed: int = 0
    failure_category: FailureCategory | None = None
    failure_message: str | None = Field(
        default=None, description="First line of the error, for tables and logs."
    )
    failure_detail: str | None = Field(
        default=None, description="Trimmed traceback that is fed back to the LLM."
    )
    output_tail: str = Field(default="", description="End of pytest's stdout/stderr.")

    @property
    def passed(self) -> bool:
        return self.status is ExecutionStatus.PASSED


class AttemptKind(StrEnum):
    GENERATE = "generate"
    REPAIR = "repair"


class AttemptOutcome(StrEnum):
    PASSED = "passed"
    STATIC_FAILED = "static_failed"
    EXECUTION_FAILED = "execution_failed"
    PROVIDER_ERROR = "provider_error"


class LLMCallInfo(BaseModel):
    latency_s: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    retries: int = 0
    prompt_chars: int = 0
    response_chars: int = 0


class Attempt(BaseModel):
    """One LLM call plus everything that happened to its output."""

    number: int = Field(ge=1)
    kind: AttemptKind
    started_at: datetime
    llm: LLMCallInfo | None = None
    issues: list[Issue] = Field(default_factory=list)
    execution: ExecutionResult | None = None
    outcome: AttemptOutcome
    failure_category: FailureCategory | None = None
    failure_message: str | None = None
    artifacts: dict[str, str] = Field(
        default_factory=dict,
        description="Paths relative to the run directory: prompt, response, code, pytest output.",
    )


class FinalStatus(StrEnum):
    PASSED_FIRST_ATTEMPT = "passed_first_attempt"
    PASSED_AFTER_REPAIR = "passed_after_repair"
    FAILED = "failed"


class StoryResult(BaseModel):
    story: Story
    attempts: list[Attempt] = Field(default_factory=list)
    final_status: FinalStatus
    final_test: str | None = Field(
        default=None, description="Path of the passing test, relative to the run directory."
    )
    duration_s: float = 0.0

    @property
    def passed(self) -> bool:
        return self.final_status is not FinalStatus.FAILED


class RunMetadata(BaseModel):
    run_id: str
    mode: Literal["run", "generate"] = Field(
        description="'run' executes tests in a browser; 'generate' stops after static checks."
    )
    started_at: datetime
    finished_at: datetime | None = None
    provider: str
    model: str
    options: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    base_url: str
    max_repairs: int
    prompt_version: str
    catalog_sha256: str
    versions: dict[str, str] = Field(default_factory=dict)
    platform: str = ""


class RunLog(BaseModel):
    """The attempt log written to ``attempts.json`` for every run."""

    schema_version: int = ATTEMPT_LOG_SCHEMA_VERSION
    meta: RunMetadata
    results: list[StoryResult] = Field(default_factory=list)
