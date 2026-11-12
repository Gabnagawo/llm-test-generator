"""Run one generated test with pytest-playwright and turn the outcome into data.

Every test runs in its own ``pytest`` subprocess, rooted at the run directory with
its own ``pytest.ini`` and ``conftest.py``, so this project's pytest options and
coverage settings never leak into the generated tests.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from defusedxml import ElementTree

from llm_test_generator.models import ExecutionResult, ExecutionStatus, FailureCategory

ACTION_TIMEOUT_MS = 5_000
NAVIGATION_TIMEOUT_MS = 20_000
MAX_DETAIL_CHARS = 3_000
MAX_TAIL_CHARS = 4_000
_LOCATION_RE = re.compile(r"test_\w+\.py:\d+")

PYTEST_INI = """\
[pytest]
# Written by llm-test-generator: isolates generated tests from the project's own config.
addopts = -p no:cacheprovider
filterwarnings = ignore::DeprecationWarning
"""

CONFTEST = f'''\
"""Harness for generated tests (written by llm-test-generator)."""

import pytest
from playwright.sync_api import Page, Playwright, expect

TEST_ID_ATTRIBUTE = "{{test_id_attribute}}"


@pytest.fixture(scope="session", autouse=True)
def _test_id_attribute(playwright: Playwright) -> None:
    playwright.selectors.set_test_id_attribute(TEST_ID_ATTRIBUTE)


@pytest.fixture(autouse=True)
def _fail_fast(page: Page) -> None:
    # Playwright's 30 s default turns every wrong selector into a 30 s wait.
    page.set_default_timeout({ACTION_TIMEOUT_MS})
    page.set_default_navigation_timeout({NAVIGATION_TIMEOUT_MS})
    expect.set_options(timeout={ACTION_TIMEOUT_MS})
'''


def prepare_run_dir(run_dir: Path, test_id_attribute: str = "data-test") -> None:
    """Write the isolated pytest config and harness conftest into a run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "pytest.ini").write_text(PYTEST_INI, encoding="utf-8", newline="\n")
    conftest = CONFTEST.replace("{test_id_attribute}", test_id_attribute)
    (run_dir / "conftest.py").write_text(conftest, encoding="utf-8", newline="\n")


_RULES: list[tuple[re.Pattern[str], FailureCategory]] = [
    (re.compile(r"strict mode violation", re.I), FailureCategory.STRICT_MODE_VIOLATION),
    (re.compile(r"net::ERR_|NS_ERROR_|Page\.goto: ", re.I), FailureCategory.NAVIGATION_ERROR),
    (re.compile(r"(Locator|Page)\.\w+: Timeout \d+ms exceeded"), FailureCategory.LOCATOR_TIMEOUT),
    (re.compile(r"TimeoutError"), FailureCategory.LOCATOR_TIMEOUT),
    (
        re.compile(r"AssertionError|Locator expected|Page URL expected|assert "),
        FailureCategory.ASSERTION_FAILED,
    ),
    (
        re.compile(r"\b(NameError|TypeError|AttributeError|ValueError|KeyError|IndexError)\b"),
        FailureCategory.PYTHON_ERROR,
    ),
    (
        re.compile(r"ImportError|ModuleNotFoundError|SyntaxError|ERROR collecting"),
        FailureCategory.COLLECTION_ERROR,
    ),
]


def classify_failure(text: str) -> FailureCategory:
    for pattern, category in _RULES:
        if pattern.search(text):
            return category
    return FailureCategory.OTHER


def trim_detail(text: str, limit: int = MAX_DETAIL_CHARS) -> str:
    """Reduce a pytest traceback to what a model can act on.

    Keeps the failing line of the generated test (pytest marks it with ``>`` in the
    first frame), its location, and the ``E`` lines with Playwright's message and call
    log. Frames inside Playwright itself are dropped.
    """
    lines = text.strip().splitlines()
    failing = next((ln[1:].strip() for ln in lines if ln.startswith(">")), None)
    location = next((m.group(0) for ln in lines if (m := _LOCATION_RE.search(ln))), None)
    errors = [ln[1:].strip() for ln in lines if ln.startswith("E ")]
    if not errors:
        out = "\n".join(lines[-40:])
    else:
        head = []
        if failing:
            head.append(f"Failing line{f' ({location})' if location else ''}: {failing}")
        out = "\n".join([*head, *errors[:40]])
    if len(out) > limit:
        out = out[: limit // 2] + "\n[...]\n" + out[-limit // 2 :]
    return out


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = re.sub(r"^E\s+", "", line.strip()).strip()
        if stripped:
            return stripped[:300]
    return ""


def parse_junit(path: Path) -> tuple[int, int, str | None]:
    """Return (tests, passed, failure text of the first failing case)."""
    root = ElementTree.parse(path).getroot()
    if root is None:  # pragma: no cover - pytest always writes a root element
        return 0, 0, None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = failed = skipped = 0
    detail: str | None = None
    for suite in suites:
        total += int(suite.get("tests", "0"))
        failed += int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
        skipped += int(suite.get("skipped", "0"))
        for case in suite.iter("testcase"):
            for tag in ("failure", "error"):
                node = case.find(tag)
                if node is not None and detail is None:
                    detail = (node.text or "") or (node.get("message") or "")
    return total, total - failed - skipped, detail


def run_test(
    test_file: Path,
    run_dir: Path,
    base_url: str,
    timeout_s: float = 120.0,
    browser: str = "chromium",
    headed: bool = False,
) -> ExecutionResult:
    """Execute ``test_file`` (which must live under ``run_dir``) and classify the result."""
    # pytest runs with cwd=run_dir, so relative paths would be resolved twice.
    test_file, run_dir = test_file.resolve(), run_dir.resolve()
    junit = test_file.with_suffix(".junit.xml")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_file),
        "-c",
        str(run_dir / "pytest.ini"),
        "--rootdir",
        str(run_dir),
        "--base-url",
        base_url,
        "--browser",
        browser,
        f"--junitxml={junit}",
        "-q",
        "--no-header",
        "-rN",
    ]
    if headed:
        cmd.append("--headed")
    start = time.perf_counter()
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv; the test file is ours
            cmd, capture_output=True, text=True, timeout=timeout_s, check=False, cwd=run_dir
        )
    except subprocess.TimeoutExpired as exc:
        tail = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else exc.stdout or ""
        return ExecutionResult(
            status=ExecutionStatus.TIMEOUT,
            duration_s=round(time.perf_counter() - start, 2),
            failure_category=FailureCategory.EXECUTION_TIMEOUT,
            failure_message=f"pytest did not finish within {timeout_s:.0f} s",
            failure_detail=f"The whole test took longer than {timeout_s:.0f} s and was killed.",
            output_tail=tail[-MAX_TAIL_CHARS:],
        )
    duration = round(time.perf_counter() - start, 2)
    output = (proc.stdout + proc.stderr).strip()
    tail = output[-MAX_TAIL_CHARS:]

    total = passed = 0
    detail: str | None = None
    if junit.exists():
        total, passed, detail = parse_junit(junit)

    if proc.returncode == 0 and total > 0 and passed == total:
        return ExecutionResult(
            status=ExecutionStatus.PASSED,
            duration_s=duration,
            exit_code=0,
            tests_total=total,
            tests_passed=passed,
            output_tail=tail,
        )
    if proc.returncode == 5 or (proc.returncode == 0 and total == 0):
        return ExecutionResult(
            status=ExecutionStatus.NO_TESTS,
            duration_s=duration,
            exit_code=proc.returncode,
            failure_category=FailureCategory.NO_TESTS_RAN,
            failure_message="pytest collected no tests",
            failure_detail="pytest collected no tests from the file.",
            output_tail=tail,
        )
    text = detail or output
    status = ExecutionStatus.FAILED if proc.returncode == 1 else ExecutionStatus.ERROR
    category = classify_failure(text)
    if proc.returncode in (2, 3, 4) and category is FailureCategory.OTHER:
        category = FailureCategory.COLLECTION_ERROR
    return ExecutionResult(
        status=status,
        duration_s=duration,
        exit_code=proc.returncode,
        tests_total=total,
        tests_passed=passed,
        failure_category=category,
        failure_message=_first_line(_error_lines(text)) or _first_line(text),
        failure_detail=trim_detail(text),
        output_tail=tail,
    )


def _error_lines(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if ln.startswith("E "))
