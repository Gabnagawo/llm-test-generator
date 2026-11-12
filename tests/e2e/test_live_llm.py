"""One real generation against a running Ollama. Run: pytest -m live."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_test_generator.catalog import load_catalog
from llm_test_generator.config import Settings
from llm_test_generator.pipeline import Pipeline, PipelineConfig
from llm_test_generator.providers import build_provider
from llm_test_generator.stories import load_stories
from tests.conftest import ROOT

pytestmark = pytest.mark.live


def test_one_story_generates_a_statically_valid_test(tmp_path: Path) -> None:
    stories = load_stories([ROOT / "examples" / "stories" / "01-authentication.md"])[:1]
    pipeline = Pipeline(
        build_provider(Settings()),
        load_catalog(),
        tmp_path / "run",
        PipelineConfig(mode="generate", max_repairs=1),
    )
    log = pipeline.run(stories)
    assert log.results[0].passed, log.results[0].attempts[-1].failure_message
