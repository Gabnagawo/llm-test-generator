"""Prompt templates. Bump ``PROMPT_VERSION`` whenever the wording changes.

The version is stored in every run log, so results from different prompt versions
are never compared as if they were the same experiment.
"""

from __future__ import annotations

from llm_test_generator.catalog import Catalog
from llm_test_generator.models import ChatMessage, ExecutionResult, Issue, Story

PROMPT_VERSION = "2026-11-12.1"

SYSTEM_PROMPT = """\
You are a senior SDET. You write one Playwright end-to-end test in Python (pytest + \
pytest-playwright, sync API) for one user story.

Hard rules:
1. Output exactly one ```python code block and nothing else.
2. Imports allowed: `from playwright.sync_api import Page, expect`, `import re`, `import pytest`.
3. Define exactly one test function, named as requested, taking the `page: Page` fixture.
4. Navigate with relative paths only, e.g. page.goto("/"). The base URL is configured.
5. Locate elements with page.get_by_test_id("<id>") using ONLY ids from the page catalog. \
page.get_by_role / get_by_text / get_by_placeholder are allowed when no test id exists. \
Never invent test ids, CSS classes or XPath.
6. Assert every acceptance criterion with Playwright's web-first assertions: \
expect(locator).to_have_text(...), to_contain_text, to_be_visible, to_have_count, \
to_have_value, expect(page).to_have_url(re.compile(...)). Use expect(locator).not_to_be_visible() \
or to_have_count(0) for absent elements.
7. No sleeps: no time.sleep and no page.wait_for_timeout. Playwright waits automatically.
8. Each test starts in a fresh, logged-out browser context: perform the story's setup \
(including logging in) inside the test.
9. When several elements share a test id, narrow them with .first, .last, .nth(i) or \
.filter(has_text=...)."""

EXAMPLE = """\
```python
import re

from playwright.sync_api import Page, expect


def test_footer_shows_social_links(page: Page) -> None:
    # Deliberately not one of the benchmark stories: it only shows the expected shape.
    page.goto("/")
    page.get_by_test_id("username").fill("visual_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\\.html$"))
    expect(page.get_by_test_id("social-linkedin")).to_be_visible()
    expect(page.get_by_test_id("footer-copy")).to_contain_text("Sauce Labs")
```"""


def render_story(story: Story) -> str:
    lines = [f"Title: {story.title}"]
    if story.narrative:
        lines.append(f"Narrative: {story.narrative}")
    lines.append("Acceptance criteria:")
    lines.extend(f"- {c}" for c in story.criteria)
    return "\n".join(lines)


def generation_messages(story: Story, catalog: Catalog) -> list[ChatMessage]:
    user = (
        f"Page catalog (captured from the live app):\n{catalog.render()}\n\n"
        f"Format example (a different story):\n{EXAMPLE}\n\n"
        f"Write the test function `{story.test_name}` for this story:\n{render_story(story)}"
    )
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user),
    ]


def static_feedback(issues: list[Issue], catalog: Catalog, unknown_ids: list[str]) -> str:
    lines = ["Your test was rejected by static validation before it ran:"]
    lines.extend(f"- {issue.render()}" for issue in issues)
    for test_id in unknown_ids:
        close = catalog.suggest(test_id)
        hint = ", ".join(f'"{c}"' for c in close) if close else "none"
        lines.append(f'- "{test_id}" is not in the catalog. Closest catalog ids: {hint}')
    lines.append("Fix every problem and reply with the complete corrected test in one code block.")
    return "\n".join(lines)


def execution_feedback(result: ExecutionResult) -> str:
    detail = result.failure_detail or result.output_tail or "(no output captured)"
    return (
        f"The test ran against the live app and failed ({result.status.value}, "
        f"category: {result.failure_category.value if result.failure_category else 'unknown'}).\n"
        f"Error:\n```text\n{detail}\n```\n"
        "Decide whether the test or your assumption about the page is wrong, using the page "
        "catalog. Keep every assertion that the acceptance criteria require; do not delete "
        "assertions just to make the test pass. Reply with the complete corrected test in one "
        "code block."
    )


def repair_messages(
    history: list[ChatMessage], previous_answer: str, feedback: str
) -> list[ChatMessage]:
    """Continue the conversation: the model sees its own answer and what went wrong."""
    return [
        *history,
        ChatMessage(role="assistant", content=previous_answer),
        ChatMessage(role="user", content=feedback),
    ]
