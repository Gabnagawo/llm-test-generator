from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from llm_test_generator.catalog import Catalog
from llm_test_generator.cli import app
from llm_test_generator.models import RunLog, Story
from llm_test_generator.pipeline import Pipeline, PipelineConfig
from llm_test_generator.providers import FakeProvider
from llm_test_generator.report import comparison_table, load_run, render_markdown, summarize
from tests.conftest import GOOD_TEST, ROOT, fenced
from tests.test_pipeline import FAIL, PASS, ScriptedExecutor

runner = CliRunner()


@pytest.fixture
def mixed_log(tmp_path: Path, catalog: Catalog, story: Story) -> RunLog:
    """Three stories: pass first try, pass after one repair, fail after two repairs."""
    stories = [story.model_copy(update={"id": i}) for i in ("a", "b", "c")]
    answers = [
        fenced(GOOD_TEST.replace("test_successful_login", "test_a")),
        fenced(GOOD_TEST.replace("test_successful_login", "test_b")),
        fenced(GOOD_TEST.replace("test_successful_login", "test_b")),
        "no code at all",
    ]
    provider = FakeProvider(answers, model="qwen3:8b")
    executor = ScriptedExecutor(PASS, FAIL, PASS)
    pipeline = Pipeline(
        provider, catalog, tmp_path / "run", PipelineConfig(run_lint=False), executor=executor
    )
    return pipeline.run(stories)


def test_summarize(mixed_log: RunLog) -> None:
    s = summarize(mixed_log)
    assert (s.stories, s.passed_first, s.passed_by_attempt, s.failed) == (3, 1, [1, 2, 2], 1)
    assert s.passed_final == 2
    assert (s.llm_calls, s.static_rejections, s.execution_failures) == (6, 3, 1)
    assert s.first_attempt_failures == {"locator_timeout": 1, "no_code": 1}
    assert s.all_failures == {"no_code": 3, "locator_timeout": 1}
    assert s.rate(2) == "2/3 (67 %)"
    assert s.label == "fake qwen3:8b"


def test_markdown_report(mixed_log: RunLog) -> None:
    text = render_markdown([mixed_log])
    assert "| fake qwen3:8b | 3 | 1/3 (33 %) | 2/3 (67 %) | 2/3 (67 %) | 1 | 6 |" in text
    assert "| b | 2 | passed_after_repair | locator_timeout -> pass |" in text
    assert "| c | 3 | failed | no_code -> no_code -> no_code |" in text
    assert "passed against the live app" in text


def test_report_labels_thinking_mode(mixed_log: RunLog) -> None:
    mixed_log.meta.options["think"] = True
    assert summarize(mixed_log).label == "fake qwen3:8b (think=on)"
    assert comparison_table([]).count("\n") == 1


def test_cli_stories_and_catalog_show() -> None:
    result = runner.invoke(app, ["stories", str(ROOT / "examples" / "stories")])
    assert result.exit_code == 0
    assert "sorting-by-price-from-low-to-high" in result.output
    shown = runner.invoke(app, ["catalog", "show"])
    assert shown.exit_code == 0
    assert "13 page states" in shown.output


def test_cli_version_and_bad_input(tmp_path: Path) -> None:
    assert "llm-test-generator 0.1.0" in runner.invoke(app, ["--version"]).output
    bad = runner.invoke(app, ["stories", str(tmp_path / "x.txt")])
    assert bad.exit_code == 2
    only = runner.invoke(app, ["run", str(ROOT / "examples" / "stories"), "--only", "nope"])
    assert only.exit_code == 2
    assert "unknown story id" in only.output
    mode = runner.invoke(app, ["run", "--mode", "fast"])
    assert mode.exit_code != 0


def test_cli_check(tmp_path: Path) -> None:
    good = tmp_path / "test_successful_login.py"
    good.write_text(GOOD_TEST, encoding="utf-8")
    assert runner.invoke(app, ["check", str(good)]).exit_code == 0
    bad = tmp_path / "test_x.py"
    bad.write_text(GOOD_TEST.replace('"username"', '"user-name"'), encoding="utf-8")
    result = runner.invoke(app, ["check", str(bad), "--test-name", "test_successful_login"])
    assert result.exit_code == 1
    assert "[unknown-test-id]" in result.output


def test_cli_run_and_report_with_fake_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    result = runner.invoke(
        app,
        [
            "run",
            str(ROOT / "examples" / "stories" / "01-authentication.md"),
            "--only",
            "successful-login",
            "--mode",
            "generate",
            "--max-repairs",
            "1",
            "--out",
            str(tmp_path),
            "--run-id",
            "fake-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "1 stories, fake fake, mode=generate, max repairs=1" in result.output
    assert "no_code" in result.output
    assert "valid on 1st attempt: 0/1 (0 %)" in result.output
    log = load_run(tmp_path / "fake-run")
    assert len(log.results[0].attempts) == 2

    out = tmp_path / "report.md"
    rep = runner.invoke(app, ["report", str(tmp_path / "fake-run"), "-o", str(out)])
    assert rep.exit_code == 0
    assert "## Comparison" in out.read_text(encoding="utf-8")
    printed = runner.invoke(app, ["report", str(tmp_path / "fake-run" / "attempts.json")])
    assert "| successful-login | 2 | failed |" in printed.output


def test_cli_run_reports_config_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    result = runner.invoke(app, ["run", str(ROOT / "examples" / "stories")])
    assert result.exit_code == 2
    assert "needs LLM_MODEL" in result.output
