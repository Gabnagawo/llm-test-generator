from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from llm_test_generator.catalog import Catalog
from llm_test_generator.models import (
    AttemptKind,
    AttemptOutcome,
    ExecutionResult,
    ExecutionStatus,
    FailureCategory,
    FinalStatus,
    RunLog,
    Story,
)
from llm_test_generator.pipeline import Pipeline, PipelineConfig, new_run_id
from llm_test_generator.prompts import PROMPT_VERSION
from llm_test_generator.providers import FakeProvider
from tests.conftest import GOOD_TEST, fenced

PASS = ExecutionResult(status=ExecutionStatus.PASSED, duration_s=1.0, tests_total=1, tests_passed=1)
FAIL = ExecutionResult(
    status=ExecutionStatus.FAILED,
    duration_s=6.0,
    exit_code=1,
    failure_category=FailureCategory.LOCATOR_TIMEOUT,
    failure_message="TimeoutError: Locator.click: Timeout 5000ms exceeded.",
    failure_detail='Failing line: page.get_by_test_id("checkout").click()',
)


class ScriptedExecutor:
    def __init__(self, *results: ExecutionResult) -> None:
        self.results = list(results)
        self.files: list[Path] = []

    def __call__(self, test_file: Path, run_dir: Path) -> ExecutionResult:
        assert test_file.is_file()
        assert (run_dir / "conftest.py").is_file()
        self.files.append(test_file)
        return self.results.pop(0)


def make(
    tmp_path: Path,
    catalog: Catalog,
    answers: list[str],
    executor: ScriptedExecutor | None = None,
    **config: object,
) -> tuple[Pipeline, FakeProvider]:
    provider = FakeProvider(answers)
    pipeline = Pipeline(
        provider,
        catalog,
        tmp_path / "run",
        PipelineConfig(run_lint=False, **config),  # type: ignore[arg-type]
        executor=executor or ScriptedExecutor(PASS, PASS, PASS),
    )
    return pipeline, provider


def test_passes_on_first_attempt_and_writes_artifacts(
    tmp_path: Path, catalog: Catalog, story: Story
) -> None:
    pipeline, provider = make(tmp_path, catalog, [fenced(GOOD_TEST)])
    log = pipeline.run([story])
    (result,) = log.results
    assert result.final_status is FinalStatus.PASSED_FIRST_ATTEMPT
    assert [a.outcome for a in result.attempts] == [AttemptOutcome.PASSED]
    run = tmp_path / "run"
    assert (run / "passing" / "test_successful_login.py").read_text(encoding="utf-8") == GOOD_TEST
    assert result.final_test == "successful-login/attempt-1/test_successful_login.py"
    artifacts = result.attempts[0].artifacts
    assert set(artifacts) == {"prompt", "response", "code", "pytest"}
    assert all((run / p).is_file() for p in artifacts.values())
    saved = RunLog.model_validate_json((run / "attempts.json").read_text(encoding="utf-8"))
    assert saved.meta.prompt_version == PROMPT_VERSION
    assert saved.meta.finished_at is not None
    assert saved.meta.catalog_sha256 == catalog.sha256()
    assert len(provider.calls) == 1


def test_static_failure_is_repaired_with_catalog_hints(
    tmp_path: Path, catalog: Catalog, story: Story
) -> None:
    bad = GOOD_TEST.replace('"username"', '"user-name"')
    executor = ScriptedExecutor(PASS)
    pipeline, provider = make(tmp_path, catalog, [fenced(bad), fenced(GOOD_TEST)], executor)
    (result,) = pipeline.run([story]).results
    assert result.final_status is FinalStatus.PASSED_AFTER_REPAIR
    first, second = result.attempts
    assert first.outcome is AttemptOutcome.STATIC_FAILED
    assert first.failure_category is FailureCategory.UNKNOWN_SELECTOR
    assert first.execution is None
    assert second.kind is AttemptKind.REPAIR
    repair_prompt = provider.calls[1]
    assert repair_prompt[-2].role == "assistant"
    assert '"user-name" is not in the catalog. Closest catalog ids: "username"' in (
        repair_prompt[-1].content
    )
    assert len(executor.files) == 1  # the invalid attempt never reached the browser


def test_execution_failure_feedback_and_give_up_after_max_repairs(
    tmp_path: Path, catalog: Catalog, story: Story
) -> None:
    executor = ScriptedExecutor(FAIL, FAIL, FAIL)
    pipeline, provider = make(tmp_path, catalog, [fenced(GOOD_TEST)], executor, max_repairs=2)
    (result,) = pipeline.run([story]).results
    assert result.final_status is FinalStatus.FAILED
    assert len(result.attempts) == 3
    assert {a.failure_category for a in result.attempts} == {FailureCategory.LOCATOR_TIMEOUT}
    feedback = provider.calls[1][-1].content
    assert "category: locator_timeout" in feedback
    assert 'page.get_by_test_id("checkout").click()' in feedback
    assert len(provider.calls[2]) == len(provider.calls[1]) + 2  # history grows per repair
    assert not (tmp_path / "run" / "passing").exists()


def test_provider_error_stops_the_story(tmp_path: Path, catalog: Catalog, story: Story) -> None:
    pipeline, provider = make(tmp_path, catalog, ["!error connection refused"])
    (result,) = pipeline.run([story]).results
    assert result.final_status is FinalStatus.FAILED
    (attempt,) = result.attempts
    assert attempt.outcome is AttemptOutcome.PROVIDER_ERROR
    assert attempt.failure_message == "connection refused"
    assert attempt.llm is None
    assert len(provider.calls) == 1


def test_no_code_answer_has_no_code_artifact(
    tmp_path: Path, catalog: Catalog, story: Story
) -> None:
    pipeline, _ = make(tmp_path, catalog, ["I can't do that."], max_repairs=0)
    (result,) = pipeline.run([story]).results
    (attempt,) = result.attempts
    assert attempt.failure_category is FailureCategory.NO_CODE
    assert "code" not in attempt.artifacts


def test_generate_mode_never_executes(tmp_path: Path, catalog: Catalog, story: Story) -> None:
    executor = ScriptedExecutor()
    pipeline, _ = make(tmp_path, catalog, [fenced(GOOD_TEST)], executor, mode="generate")
    log = pipeline.run([story])
    assert log.meta.mode == "generate"
    assert log.results[0].final_status is FinalStatus.PASSED_FIRST_ATTEMPT
    assert executor.files == []


def test_progress_callback_and_multiple_stories(
    tmp_path: Path, catalog: Catalog, story: Story
) -> None:
    other = story.model_copy(update={"id": "other"})
    seen: list[tuple[str, int]] = []
    pipeline, _ = make(tmp_path, catalog, [fenced(GOOD_TEST)])
    pipeline.progress = lambda s, a: seen.append((s.id, a.number))
    log = pipeline.run([story, other])
    assert seen == [("successful-login", 1), ("other", 1), ("other", 2), ("other", 3)]
    # `other` expects test_other, so the answer fails structure validation 3 times
    assert log.results[1].final_status is FinalStatus.FAILED
    data = json.loads((tmp_path / "run" / "attempts.json").read_text(encoding="utf-8"))
    assert len(data["results"]) == 2


def test_new_run_id() -> None:
    now = datetime(2026, 11, 12, 18, 30, 5, tzinfo=UTC)
    assert new_run_id("qwen3:8b", now) == "20261112T183005Z-qwen3-8b"
