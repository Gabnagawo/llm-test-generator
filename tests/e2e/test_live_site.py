"""End-to-end checks against the live demo app (Chromium + network). Run: pytest -m e2e."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from llm_test_generator.catalog import load_catalog
from llm_test_generator.executor import prepare_run_dir, run_test
from tests.conftest import BASE_URL, ROOT

GENERATED = sorted((ROOT / "examples" / "generated").glob("test_*.py"))

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("test_file", GENERATED, ids=[p.stem for p in GENERATED])
def test_committed_generated_tests_still_pass(test_file: Path, tmp_path: Path) -> None:
    """The LLM-written tests in examples/generated must keep passing on the live site."""
    prepare_run_dir(tmp_path)
    copy = tmp_path / test_file.name
    shutil.copyfile(test_file, copy)
    result = run_test(copy, tmp_path, BASE_URL, timeout_s=120)
    assert result.passed, result.failure_detail


def test_catalog_has_not_drifted() -> None:
    """Re-capture the catalog and compare the set of test ids with the committed one."""
    from llm_test_generator.capture import capture_catalog

    live = capture_catalog(BASE_URL)
    committed = load_catalog()
    assert [p.name for p in live.pages] == [p.name for p in committed.pages]
    assert live.test_ids == committed.test_ids
