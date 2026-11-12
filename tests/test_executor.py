"""Executor tests that need no browser: plain pytest files run through ``run_test``."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_test_generator.executor import (
    classify_failure,
    parse_junit,
    prepare_run_dir,
    run_test,
    trim_detail,
)
from llm_test_generator.models import ExecutionStatus, FailureCategory

PLAYWRIGHT_TIMEOUT = """\
    def test_x(page):
>       page.get_by_test_id("user-name").fill("standard_user")

.venv/Lib/site-packages/playwright/_impl/_locator.py:229: in fill
    return await self._frame.fill(self._selector, strict=True, **params)
>           return await func()
E           playwright._impl._errors.TimeoutError: Locator.fill: Timeout 5000ms exceeded.
E           Call log:
E             - waiting for get_by_test_id("user-name")

runs/x/test_x.py:6: TimeoutError
"""


@pytest.mark.parametrize(
    ("text", "category"),
    [
        (PLAYWRIGHT_TIMEOUT, FailureCategory.LOCATOR_TIMEOUT),
        (
            "Error: strict mode violation: resolved to 6 elements",
            FailureCategory.STRICT_MODE_VIOLATION,
        ),
        ("AssertionError: Locator expected to have text 'x'", FailureCategory.ASSERTION_FAILED),
        ("AssertionError: Page URL expected to match", FailureCategory.ASSERTION_FAILED),
        ("Page.goto: net::ERR_NAME_NOT_RESOLVED", FailureCategory.NAVIGATION_ERROR),
        (
            "AttributeError: 'Locator' object has no attribute 'textContent'",
            FailureCategory.PYTHON_ERROR,
        ),
        ("ModuleNotFoundError: No module named 'foo'", FailureCategory.COLLECTION_ERROR),
        ("something odd", FailureCategory.OTHER),
    ],
)
def test_classify_failure(text: str, category: FailureCategory) -> None:
    assert classify_failure(text) is category


def test_trim_detail_keeps_the_test_line_and_error_lines() -> None:
    detail = trim_detail(PLAYWRIGHT_TIMEOUT)
    assert detail.splitlines() == [
        'Failing line (test_x.py:6): page.get_by_test_id("user-name").fill("standard_user")',
        "playwright._impl._errors.TimeoutError: Locator.fill: Timeout 5000ms exceeded.",
        "Call log:",
        '- waiting for get_by_test_id("user-name")',
    ]


def test_trim_detail_without_error_lines_and_long_text() -> None:
    assert trim_detail("a\nb\nc") == "a\nb\nc"
    long = trim_detail("E " + "x" * 10_000, limit=100)
    assert "[...]" in long
    assert len(long) < 120


def test_prepare_run_dir_writes_isolated_config(tmp_path: Path) -> None:
    prepare_run_dir(tmp_path / "run", "data-qa")
    conftest = (tmp_path / "run" / "conftest.py").read_text(encoding="utf-8")
    assert 'TEST_ID_ATTRIBUTE = "data-qa"' in conftest
    assert "set_default_timeout(5000)" in conftest
    assert "[pytest]" in (tmp_path / "run" / "pytest.ini").read_text(encoding="utf-8")


def test_parse_junit(tmp_path: Path) -> None:
    junit = tmp_path / "r.xml"
    junit.write_text(
        '<testsuites><testsuite tests="3" failures="1" errors="0" skipped="1">'
        '<testcase name="a"/><testcase name="b"><failure message="boom">trace</failure></testcase>'
        '<testcase name="c"><skipped/></testcase></testsuite></testsuites>',
        encoding="utf-8",
    )
    assert parse_junit(junit) == (3, 1, "trace")


@pytest.fixture
def plain_run_dir(tmp_path: Path) -> Path:
    """A run dir whose conftest needs no browser, so run_test's plumbing is testable."""
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text("", encoding="utf-8")
    return tmp_path


def write(run_dir: Path, body: str) -> Path:
    path = run_dir / "story" / "test_story.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_run_test_passed(plain_run_dir: Path) -> None:
    result = run_test(
        write(plain_run_dir, "def test_ok():\n    assert True\n"), plain_run_dir, "http://x"
    )
    assert result.status is ExecutionStatus.PASSED
    assert (result.tests_total, result.tests_passed, result.exit_code) == (1, 1, 0)
    assert result.passed


def test_run_test_assertion_failure(plain_run_dir: Path) -> None:
    result = run_test(
        write(plain_run_dir, "def test_bad():\n    assert 1 == 2, 'numbers differ'\n"),
        plain_run_dir,
        "http://x",
    )
    assert result.status is ExecutionStatus.FAILED
    assert result.failure_category is FailureCategory.ASSERTION_FAILED
    assert result.failure_message == "AssertionError: numbers differ"
    assert "Failing line (test_story.py:2)" in (result.failure_detail or "")


def test_run_test_collection_error(plain_run_dir: Path) -> None:
    result = run_test(write(plain_run_dir, "import not_a_module\n"), plain_run_dir, "http://x")
    assert result.status is ExecutionStatus.ERROR
    assert result.failure_category is FailureCategory.COLLECTION_ERROR


def test_run_test_no_tests(plain_run_dir: Path) -> None:
    result = run_test(write(plain_run_dir, "x = 1\n"), plain_run_dir, "http://x")
    assert result.status is ExecutionStatus.NO_TESTS
    assert result.failure_category is FailureCategory.NO_TESTS_RAN


def test_run_test_timeout(plain_run_dir: Path) -> None:
    body = "import time\n\n\ndef test_slow():\n    time.sleep(30)\n"
    result = run_test(write(plain_run_dir, body), plain_run_dir, "http://x", timeout_s=3)
    assert result.status is ExecutionStatus.TIMEOUT
    assert result.failure_category is FailureCategory.EXECUTION_TIMEOUT


def test_run_test_with_relative_paths(plain_run_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: pytest runs with cwd=run_dir, so relative paths used to resolve twice.
    test_file = write(plain_run_dir, "def test_ok():\n    assert True\n")
    monkeypatch.chdir(plain_run_dir.parent)
    rel_dir = Path(plain_run_dir.name)
    result = run_test(rel_dir / "story" / test_file.name, rel_dir, "http://x")
    assert result.status is ExecutionStatus.PASSED


def test_failure_message_keeps_words_starting_with_e(plain_run_dir: Path) -> None:
    body = "def test_bad():\n    raise ValueError('Expected a cart')\n"
    result = run_test(write(plain_run_dir, body), plain_run_dir, "http://x")
    assert result.failure_message == "ValueError: Expected a cart"
