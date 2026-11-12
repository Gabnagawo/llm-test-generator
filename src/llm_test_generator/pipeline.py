"""Generate -> validate -> execute -> repair, for every story, with a full attempt log.

Per story: attempt 1 is a generation. Each failed attempt (static or at run time) is
followed by a repair that sees the previous answer and the exact error, up to
``max_repairs`` times. Every prompt, answer, test file and pytest output is written to
the run directory and indexed in ``attempts.json``.
"""

from __future__ import annotations

import platform
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Literal

from llm_test_generator.catalog import Catalog
from llm_test_generator.executor import prepare_run_dir, run_test
from llm_test_generator.models import (
    Attempt,
    AttemptKind,
    AttemptOutcome,
    ChatMessage,
    ExecutionResult,
    FailureCategory,
    FinalStatus,
    LLMCallInfo,
    RunLog,
    RunMetadata,
    Story,
    StoryResult,
    ValidationReport,
)
from llm_test_generator.prompts import (
    PROMPT_VERSION,
    execution_feedback,
    generation_messages,
    repair_messages,
    static_feedback,
)
from llm_test_generator.providers import LLMProvider, ProviderError
from llm_test_generator.validate import validate

Executor = Callable[[Path, Path], ExecutionResult]
Progress = Callable[[Story, Attempt], None]
Mode = Literal["run", "generate"]


@dataclass
class PipelineConfig:
    base_url: str = "https://www.saucedemo.com"
    max_repairs: int = 2
    mode: Mode = "run"
    test_timeout_s: float = 120.0
    headed: bool = False
    run_lint: bool = True


def new_run_id(model: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    safe_model = "".join(c if c.isalnum() else "-" for c in model).strip("-")
    return f"{stamp}-{safe_model}"


def _versions() -> dict[str, str]:
    out = {"python": platform.python_version()}
    for pkg in ("llm-test-generator", "playwright", "pytest-playwright", "pytest"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:  # pragma: no cover
            out[pkg] = "unknown"
    return out


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _render_prompt(messages: Sequence[ChatMessage]) -> str:
    return "\n\n".join(f"### {m.role}\n\n{m.content}" for m in messages) + "\n"


class Pipeline:
    def __init__(
        self,
        provider: LLMProvider,
        catalog: Catalog,
        run_dir: Path,
        config: PipelineConfig | None = None,
        executor: Executor | None = None,
        progress: Progress | None = None,
    ) -> None:
        self.provider = provider
        self.catalog = catalog
        self.run_dir = run_dir
        self.config = config or PipelineConfig()
        self.progress = progress
        self._executor = executor or self._run_in_browser

    def _run_in_browser(self, test_file: Path, run_dir: Path) -> ExecutionResult:
        return run_test(
            test_file,
            run_dir,
            self.config.base_url,
            timeout_s=self.config.test_timeout_s,
            headed=self.config.headed,
        )

    @property
    def log_path(self) -> Path:
        return self.run_dir / "attempts.json"

    def run(self, stories: Sequence[Story]) -> RunLog:
        prepare_run_dir(self.run_dir, self.catalog.test_id_attribute)
        log = RunLog(
            meta=RunMetadata(
                run_id=self.run_dir.name,
                mode=self.config.mode,
                started_at=datetime.now(UTC),
                provider=self.provider.name,
                model=self.provider.model,
                options=self.provider.options(),
                base_url=self.config.base_url,
                max_repairs=self.config.max_repairs,
                prompt_version=PROMPT_VERSION,
                catalog_sha256=self.catalog.sha256(),
                versions=_versions(),
                platform=platform.platform(),
            )
        )
        for story in stories:
            log.results.append(self.run_story(story))
            self.save(log)  # survive an interrupted run
        log.meta.finished_at = datetime.now(UTC)
        self.save(log)
        return log

    def save(self, log: RunLog) -> None:
        _write(self.log_path, log.model_dump_json(indent=2) + "\n")

    def run_story(self, story: Story) -> StoryResult:
        start = time.perf_counter()
        story_dir = self.run_dir / story.id
        messages = generation_messages(story, self.catalog)
        result = StoryResult(story=story, final_status=FinalStatus.FAILED)
        for number in range(1, self.config.max_repairs + 2):
            kind = AttemptKind.GENERATE if number == 1 else AttemptKind.REPAIR
            attempt, answer, feedback = self._attempt(story, story_dir, number, kind, messages)
            result.attempts.append(attempt)
            if self.progress:
                self.progress(story, attempt)
            if attempt.outcome is AttemptOutcome.PASSED:
                result.final_status = (
                    FinalStatus.PASSED_FIRST_ATTEMPT
                    if number == 1
                    else FinalStatus.PASSED_AFTER_REPAIR
                )
                result.final_test = attempt.artifacts.get("code")
                if result.final_test:
                    passing = self.run_dir / "passing" / story.test_filename
                    passing.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(self.run_dir / result.final_test, passing)
                break
            if attempt.outcome is AttemptOutcome.PROVIDER_ERROR or feedback is None:
                break  # nothing to repair from
            messages = repair_messages(messages, answer, feedback)
        result.duration_s = round(time.perf_counter() - start, 2)
        return result

    def _attempt(
        self,
        story: Story,
        story_dir: Path,
        number: int,
        kind: AttemptKind,
        messages: list[ChatMessage],
    ) -> tuple[Attempt, str, str | None]:
        """Run one attempt. Returns the attempt, the raw answer and the repair feedback."""
        attempt_dir = story_dir / f"attempt-{number}"
        rel = attempt_dir.relative_to(self.run_dir).as_posix()
        started = datetime.now(UTC)
        prompt_text = _render_prompt(messages)
        _write(attempt_dir / "prompt.md", prompt_text)
        artifacts = {"prompt": f"{rel}/prompt.md"}

        try:
            response = self.provider.complete(messages)
        except ProviderError as exc:
            attempt = Attempt(
                number=number,
                kind=kind,
                started_at=started,
                outcome=AttemptOutcome.PROVIDER_ERROR,
                failure_category=FailureCategory.PROVIDER_ERROR,
                failure_message=str(exc)[:300],
                artifacts=artifacts,
            )
            return attempt, "", None

        _write(attempt_dir / "response.md", response.text + "\n")
        artifacts["response"] = f"{rel}/response.md"
        llm = LLMCallInfo(
            latency_s=response.latency_s,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            retries=response.retries,
            prompt_chars=len(prompt_text),
            response_chars=len(response.text),
        )
        report: ValidationReport = validate(
            response.text,
            story.test_name,
            self.catalog,
            self.config.base_url,
            run_lint=self.config.run_lint,
        )
        if report.code:
            _write(attempt_dir / story.test_filename, report.code)
            artifacts["code"] = f"{rel}/{story.test_filename}"

        if not report.ok:
            first = report.issues[0]
            attempt = Attempt(
                number=number,
                kind=kind,
                started_at=started,
                llm=llm,
                issues=report.issues,
                outcome=AttemptOutcome.STATIC_FAILED,
                failure_category=first.category,
                failure_message=first.render()[:300],
                artifacts=artifacts,
            )
            feedback = static_feedback(report.issues, self.catalog, report.unknown_ids)
            return attempt, response.text, feedback

        if self.config.mode == "generate":
            attempt = Attempt(
                number=number,
                kind=kind,
                started_at=started,
                llm=llm,
                outcome=AttemptOutcome.PASSED,
                artifacts=artifacts,
            )
            return attempt, response.text, None

        execution = self._executor(attempt_dir / story.test_filename, self.run_dir)
        _write(attempt_dir / "pytest.txt", execution.output_tail + "\n")
        artifacts["pytest"] = f"{rel}/pytest.txt"
        passed = execution.passed
        attempt = Attempt(
            number=number,
            kind=kind,
            started_at=started,
            llm=llm,
            execution=execution,
            outcome=AttemptOutcome.PASSED if passed else AttemptOutcome.EXECUTION_FAILED,
            failure_category=None if passed else execution.failure_category,
            failure_message=None if passed else execution.failure_message,
            artifacts=artifacts,
        )
        return attempt, response.text, None if passed else execution_feedback(execution)
