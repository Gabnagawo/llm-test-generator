from __future__ import annotations

import pytest

from llm_test_generator.catalog import Catalog
from llm_test_generator.models import FailureCategory
from llm_test_generator.validate import extract_code, lint, validate
from tests.conftest import BASE_URL, GOOD_TEST, fenced

NAME = "test_successful_login"


def check(code: str, catalog: Catalog, *, run_lint: bool = False):
    return validate(fenced(code), NAME, catalog, BASE_URL, run_lint=run_lint)


def test_good_test_passes_including_lint(catalog: Catalog) -> None:
    report = check(GOOD_TEST, catalog, run_lint=True)
    assert report.ok, [i.render() for i in report.issues]
    assert report.code == GOOD_TEST
    assert report.primary_category is None


class TestExtractCode:
    def test_prefers_block_with_a_test(self) -> None:
        text = "```python\nx = 1\n```\nand\n```python\ndef test_a(page):\n    pass\n```"
        assert extract_code(text) == "def test_a(page):\n    pass\n"

    def test_unlabelled_fence(self) -> None:
        assert extract_code("```\ndef test_a(page):\n    pass\n```") == (
            "def test_a(page):\n    pass\n"
        )

    def test_first_block_when_none_defines_a_test(self) -> None:
        assert extract_code("```python\nprint(1)\n```") == "print(1)\n"

    def test_bare_code_without_fence(self) -> None:
        assert extract_code("def test_a(page):\n    pass") == "def test_a(page):\n    pass\n"

    @pytest.mark.parametrize("text", ["I cannot help with that.", "```python\n```", ""])
    def test_nothing_usable(self, text: str) -> None:
        assert extract_code(text) is None


def test_no_code(catalog: Catalog) -> None:
    report = validate("Sorry, no.", NAME, catalog, BASE_URL)
    assert report.primary_category is FailureCategory.NO_CODE
    assert report.code == ""


def test_syntax_error_reports_line(catalog: Catalog) -> None:
    report = check("def test_successful_login(page):\n    page.goto('/'\n", catalog)
    assert report.primary_category is FailureCategory.SYNTAX_ERROR
    assert report.issues[0].line is not None


@pytest.mark.parametrize(
    ("code", "rule", "category"),
    [
        (
            GOOD_TEST.replace("test_successful_login", "test_login"),
            "test-name",
            FailureCategory.STRUCTURE_ERROR,
        ),
        (
            GOOD_TEST + "\n\ndef test_other(page: Page) -> None:\n    pass\n",
            "single-test",
            FailureCategory.STRUCTURE_ERROR,
        ),
        (
            GOOD_TEST.replace(
                "def test_successful_login(page: Page)",
                "async def test_successful_login(page: Page)",
            ),
            "sync-api",
            FailureCategory.STRUCTURE_ERROR,
        ),
        (
            GOOD_TEST.replace("(page: Page)", "(browser)").replace("page.", "browser."),
            "page-fixture",
            FailureCategory.STRUCTURE_ERROR,
        ),
        (
            "from playwright.sync_api import Page\n\n\n"
            "def test_successful_login(page: Page) -> None:\n"
            '    page.goto("/")\n',
            "no-assertion",
            FailureCategory.STRUCTURE_ERROR,
        ),
        (
            GOOD_TEST.replace('page.goto("/")', 'page.get_by_test_id("username").focus()'),
            "no-navigation",
            FailureCategory.STRUCTURE_ERROR,
        ),
        ("import os\n" + GOOD_TEST, "forbidden-import", FailureCategory.FORBIDDEN_CONSTRUCT),
        (
            "from subprocess import run\n" + GOOD_TEST,
            "forbidden-import",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST + '    eval("1")\n',
            "forbidden-call",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST + "    page.wait_for_timeout(1000)\n",
            "forbidden-call",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST + '    page.evaluate("localStorage.clear()")\n',
            "forbidden-call",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST.replace('page.goto("/")', 'page.goto("https://example.com/")'),
            "external-navigation",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST.replace('page.goto("/")', 'page.goto("//example.com/")'),
            "external-navigation",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST.replace(
                'page.goto("/")', 'page.goto("https://www.saucedemo.com.evil.test/")'
            ),
            "external-navigation",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST.replace('page.goto("/")', 'page.goto("javascript:alert(1)")'),
            "external-navigation",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST.replace('page.goto("/")', 'url = "/"\n    page.goto(url)'),
            "dynamic-navigation",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST + '    pytest.importorskip("os").system("id")\n',
            "forbidden-call",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST + '    getattr(page, "eva" + "luate")("1")\n',
            "forbidden-call",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST + '    re.sub.__globals__["__builtins__"]\n',
            "dunder-access",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST + '    __builtins__["ex" + "ec"]("1")\n',
            "dunder-access",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST + '    page.request.get("https://example.com/")\n',
            "forbidden-attribute",
            FailureCategory.FORBIDDEN_CONSTRUCT,
        ),
        (
            GOOD_TEST.replace('"username"', '"user-name"'),
            "unknown-test-id",
            FailureCategory.UNKNOWN_SELECTOR,
        ),
        (
            GOOD_TEST + '    page.locator("#react-burger-menu-btn").click()\n',
            "raw-selector",
            FailureCategory.UNKNOWN_SELECTOR,
        ),
        (
            GOOD_TEST + "    page.locator(\"[data-test='nope']\").click()\n",
            "unknown-test-id",
            FailureCategory.UNKNOWN_SELECTOR,
        ),
    ],
)
def test_rejections(code: str, rule: str, category: FailureCategory, catalog: Catalog) -> None:
    report = check(code, catalog)
    rules = [i.rule for i in report.issues]
    assert rule in rules
    issue = report.issues[rules.index(rule)]
    assert issue.category is category


@pytest.mark.parametrize(
    "extra",
    [
        "    page.locator('[data-test=\"shopping-cart-link\"]').click()\n",
        '    page.goto("https://www.saucedemo.com/inventory.html")\n',
        '    page.get_by_role("button", name="Open Menu").click()\n',
        "    page.get_by_test_id(f\"add-to-cart-{'x'}\").count()\n",  # dynamic ids are not checked
    ],
)
def test_allowed_constructs(extra: str, catalog: Catalog) -> None:
    report = check(GOOD_TEST + extra, catalog)
    assert report.ok, [i.render() for i in report.issues]


def test_unknown_ids_are_collected_once(catalog: Catalog) -> None:
    code = GOOD_TEST.replace('"username"', '"user-name"') + '    page.get_by_test_id("user-name")\n'
    report = check(code, catalog)
    assert report.unknown_ids == ["user-name"]


def test_lint_reports_undefined_names() -> None:
    issues = lint("def test_a(page):\n    expect(page).to_be_ok()\n")
    assert [i.rule for i in issues] == ["ruff-F821"]
    assert issues[0].category is FailureCategory.LINT_ERROR
    assert issues[0].line == 2


def test_lint_runs_only_when_structure_is_clean(catalog: Catalog) -> None:
    code = GOOD_TEST.replace(
        "from playwright.sync_api import Page, expect", "from playwright.sync_api import Page"
    )
    report = check(code, catalog, run_lint=True)
    assert {i.rule for i in report.issues} == {"ruff-F821"}
