from __future__ import annotations

from pathlib import Path

import pytest

from llm_test_generator.models import StoryFormat
from llm_test_generator.stories import (
    StoryParseError,
    load_stories,
    parse_gherkin,
    parse_markdown,
    slugify,
)
from tests.conftest import ROOT

MARKDOWN = """\
# Title of the file (ignored)

## Successful login
Tags: @smoke @auth
As a shopper, I want to log in
so that I can browse.

### Acceptance criteria
- Given I am on the login page
- When I log in as "standard_user"
  with password "secret_sauce"
1. Then I see the products

## Second story
id: Custom ID
### Criteria
* Then it works
"""

GHERKIN = """\
@cart
Feature: Cart
  A short description.

  Background:
    Given I am logged in

  # a comment
  @smoke
  Scenario: Add one
    When I add "Backpack"
    Then the badge shows "1"

  Scenario Outline: Sort by <order>
    When I sort by "<order>"
    Then the first price is "<first>"

    Examples:
      | order | first |
      | lohi  | $7.99 |
      | hilo  | $49.99 |
"""


def test_markdown_story() -> None:
    first, second = parse_markdown(MARKDOWN, "a.md")
    assert first.id == "successful-login"
    assert first.tags == ["smoke", "auth"]
    assert first.narrative == "As a shopper, I want to log in so that I can browse."
    assert first.criteria == [
        "Given I am on the login page",
        'When I log in as "standard_user" with password "secret_sauce"',
        "Then I see the products",
    ]
    assert first.format is StoryFormat.MARKDOWN
    assert first.test_name == "test_successful_login"
    assert first.test_filename == "test_successful_login.py"
    assert "Successful login" in first.text
    assert second.id == "custom-id"
    assert second.criteria == ["Then it works"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("no sections here", "no '## <title>'"),
        ("## Story\nJust prose, no criteria.", "no acceptance criteria"),
    ],
)
def test_markdown_errors(text: str, message: str) -> None:
    with pytest.raises(StoryParseError, match=message):
        parse_markdown(text)


def test_gherkin_background_tags_and_outline() -> None:
    add, lohi, hilo = parse_gherkin(GHERKIN, "cart.feature")
    assert add.id == "add-one"
    assert add.criteria == [
        "Given I am logged in",
        'When I add "Backpack"',
        'Then the badge shows "1"',
    ]
    assert add.tags == ["cart", "smoke"]
    assert add.narrative == "Feature: Cart A short description."
    assert lohi.title == "Sort by lohi #1"
    assert lohi.criteria[-1] == 'Then the first price is "$7.99"'
    assert hilo.id == "sort-by-hilo-2"
    assert hilo.format is StoryFormat.GHERKIN


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Feature: x\n", "no Scenario"),
        ("Feature: x\n  Scenario: empty\n", "has no steps"),
        ("Feature: x\n  Scenario Outline: o <a>\n    Given <a>\n", "needs an Examples table"),
    ],
)
def test_gherkin_errors(text: str, message: str) -> None:
    with pytest.raises(StoryParseError, match=message):
        parse_gherkin(text)


def test_slugify() -> None:
    assert slugify("Sorting by name (Z to A)!") == "sorting-by-name-z-to-a"
    assert slugify("???") == "story"


def test_bundled_examples_parse() -> None:
    stories = load_stories([ROOT / "examples" / "stories"])
    assert len(stories) == 12
    assert len({s.id for s in stories}) == 12
    assert {s.format for s in stories} == {StoryFormat.MARKDOWN, StoryFormat.GHERKIN}


def test_load_files_and_errors(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(MARKDOWN, encoding="utf-8")
    (tmp_path / "b.feature").write_text(GHERKIN, encoding="utf-8")
    assert len(load_stories([tmp_path / "a.md", tmp_path / "b.feature"])) == 5

    with pytest.raises(StoryParseError, match=r"expected a \.md or \.feature"):
        load_stories([tmp_path / "notes.txt"])

    (tmp_path / "c.md").write_text(MARKDOWN, encoding="utf-8")
    with pytest.raises(StoryParseError, match="duplicate story id"):
        load_stories([tmp_path])

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(StoryParseError, match="no stories found"):
        load_stories([empty])
