"""Static checks that run before a generated test is allowed near a browser.

Cheap failures (no code, syntax errors, invented selectors, sleeps, imports of ``os``)
are caught here in milliseconds and sent back to the LLM with a precise message,
instead of costing a browser run and a 5-second locator timeout.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass, field

from llm_test_generator.catalog import Catalog
from llm_test_generator.models import FailureCategory, Issue, ValidationReport

_FENCE_RE = re.compile(r"```[ \t]*(?:python|py)?[ \t]*\n(.*?)```", flags=re.DOTALL | re.IGNORECASE)
_DATA_TEST_RE = re.compile(r"""\[data-test\s*[~|^$*]?=\s*["']?([^"'\]]+)["']?\s*\]""")

ALLOWED_IMPORTS = frozenset({"playwright.sync_api", "re", "pytest"})
FORBIDDEN_CALLS = frozenset(
    {"eval", "exec", "compile", "open", "__import__", "input", "breakpoint"}
)
FORBIDDEN_METHODS = {
    "wait_for_timeout": "fixed waits make tests slow and flaky; use expect(...) auto-waiting",
    "sleep": "fixed waits make tests slow and flaky; use expect(...) auto-waiting",
    "evaluate": "JavaScript evaluation bypasses what a user can do; use locators",
    "set_test_id_attribute": "the test id attribute is configured by the harness",
}
LOCATOR_METHODS = frozenset(
    {"locator", "query_selector", "query_selector_all", "wait_for_selector"}
)
LINT_RULES = "E9,F63,F7,F82,F811"


def extract_code(text: str) -> str | None:
    """Return the Python code in an LLM answer: the fenced block, or the bare text if it parses.

    When several fenced blocks are present the one that defines a test wins.
    """
    blocks: list[str] = [str(b).strip() for b in _FENCE_RE.findall(text)]
    for block in blocks:
        if "def test_" in block:
            return block + "\n"
    if blocks:
        return blocks[0] + "\n" if blocks[0] else None
    stripped = text.strip()
    if "def test_" in stripped:
        return stripped + "\n"
    return None


@dataclass
class _Visitor(ast.NodeVisitor):
    catalog: Catalog
    base_url: str
    issues: list[Issue] = field(default_factory=list)
    unknown_ids: list[str] = field(default_factory=list)
    expect_calls: int = 0
    goto_calls: int = 0

    def add(self, rule: str, category: FailureCategory, message: str, node: ast.AST) -> None:
        self.issues.append(
            Issue(rule=rule, category=category, message=message, line=getattr(node, "lineno", None))
        )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name not in ALLOWED_IMPORTS:
                self.add(
                    "forbidden-import",
                    FailureCategory.FORBIDDEN_CONSTRUCT,
                    f"import of {alias.name!r} is not allowed (allowed: {sorted(ALLOWED_IMPORTS)})",
                    node,
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if (node.module or "") not in ALLOWED_IMPORTS:
            self.add(
                "forbidden-import",
                FailureCategory.FORBIDDEN_CONSTRUCT,
                f"import from {node.module!r} is not allowed (allowed: {sorted(ALLOWED_IMPORTS)})",
                node,
            )

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in FORBIDDEN_CALLS:
                self.add(
                    "forbidden-call",
                    FailureCategory.FORBIDDEN_CONSTRUCT,
                    f"{func.id}() is not allowed in a generated test",
                    node,
                )
            elif func.id == "expect":
                self.expect_calls += 1
        elif isinstance(func, ast.Attribute):
            self._check_method(func.attr, node)
        self.generic_visit(node)

    def _check_method(self, method: str, node: ast.Call) -> None:
        literal = _first_str_arg(node)
        if method in FORBIDDEN_METHODS:
            self.add(
                "forbidden-call",
                FailureCategory.FORBIDDEN_CONSTRUCT,
                f".{method}() is not allowed: {FORBIDDEN_METHODS[method]}",
                node,
            )
        elif method == "goto":
            self.goto_calls += 1
            if (
                literal
                and re.match(r"^[a-z]+://", literal)
                and not literal.startswith(self.base_url.rstrip("/"))
            ):
                self.add(
                    "external-navigation",
                    FailureCategory.FORBIDDEN_CONSTRUCT,
                    f"page.goto({literal!r}) leaves the app under test; use a relative path",
                    node,
                )
        elif method == "get_by_test_id" and literal is not None:
            self._check_test_id(literal, node)
        elif method in LOCATOR_METHODS and literal is not None:
            ids = _DATA_TEST_RE.findall(literal)
            if not ids:
                self.add(
                    "raw-selector",
                    FailureCategory.UNKNOWN_SELECTOR,
                    f"selector {literal!r} is not from the page catalog; "
                    'use page.get_by_test_id("<catalog id>")',
                    node,
                )
            for test_id in ids:
                self._check_test_id(test_id, node)

    def _check_test_id(self, test_id: str, node: ast.AST) -> None:
        if test_id not in self.catalog.test_ids:
            self.unknown_ids.append(test_id)
            self.add(
                "unknown-test-id",
                FailureCategory.UNKNOWN_SELECTOR,
                f"test id {test_id!r} does not exist in the page catalog",
                node,
            )


def _first_str_arg(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


def _check_structure(tree: ast.Module, test_name: str) -> list[Issue]:
    issues: list[Issue] = []
    tests = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test")
    ]
    names = [t.name for t in tests]
    if test_name not in names:
        found = ", ".join(names) or "none"
        issues.append(
            Issue(
                rule="test-name",
                category=FailureCategory.STRUCTURE_ERROR,
                message=f"expected one test function named {test_name!r}; found: {found}",
            )
        )
    elif len(tests) > 1:
        issues.append(
            Issue(
                rule="single-test",
                category=FailureCategory.STRUCTURE_ERROR,
                message=f"write exactly one test function; found {len(tests)}: {', '.join(names)}",
            )
        )
    for test in tests:
        if isinstance(test, ast.AsyncFunctionDef):
            issues.append(
                Issue(
                    rule="sync-api",
                    category=FailureCategory.STRUCTURE_ERROR,
                    message=f"{test.name} is async; use the sync Playwright API",
                    line=test.lineno,
                )
            )
        if test.name == test_name and "page" not in [a.arg for a in test.args.args]:
            issues.append(
                Issue(
                    rule="page-fixture",
                    category=FailureCategory.STRUCTURE_ERROR,
                    message=f"{test.name} must take the pytest-playwright `page` fixture",
                    line=test.lineno,
                )
            )
    return issues


def lint(code: str) -> list[Issue]:
    """Pyflakes-level errors (undefined names, redefinitions) through ruff."""
    proc = subprocess.run(  # noqa: S603 - fixed argv, code is passed on stdin
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--select",
            LINT_RULES,
            "--output-format",
            "concise",
            "--stdin-filename",
            "generated_test.py",
            "-",
        ],
        input=code,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    issues = []
    for line in proc.stdout.splitlines():
        match = re.match(r"^.*?:(\d+):\d+: ([A-Z]+\d+) (.*)$", line)
        if match:
            issues.append(
                Issue(
                    rule=f"ruff-{match.group(2)}",
                    category=FailureCategory.LINT_ERROR,
                    message=match.group(3),
                    line=int(match.group(1)),
                )
            )
    return issues


def validate(
    answer: str, test_name: str, catalog: Catalog, base_url: str, run_lint: bool = True
) -> ValidationReport:
    """Validate an LLM answer. ``report.ok`` means the test may be executed."""
    code = extract_code(answer)
    if code is None:
        return ValidationReport(
            code="",
            issues=[
                Issue(
                    rule="no-code",
                    category=FailureCategory.NO_CODE,
                    message="the answer contains no ```python code block with a test function",
                )
            ],
        )
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return ValidationReport(
            code=code,
            issues=[
                Issue(
                    rule="syntax",
                    category=FailureCategory.SYNTAX_ERROR,
                    message=f"{exc.msg}",
                    line=exc.lineno,
                )
            ],
        )
    issues = _check_structure(tree, test_name)
    visitor = _Visitor(catalog=catalog, base_url=base_url)
    visitor.visit(tree)
    issues.extend(visitor.issues)
    if visitor.expect_calls == 0:
        issues.append(
            Issue(
                rule="no-assertion",
                category=FailureCategory.STRUCTURE_ERROR,
                message="the test has no expect(...) assertion, so it cannot fail",
            )
        )
    if visitor.goto_calls == 0:
        issues.append(
            Issue(
                rule="no-navigation",
                category=FailureCategory.STRUCTURE_ERROR,
                message='the test never calls page.goto(...); start with page.goto("/")',
            )
        )
    if run_lint and not issues:
        issues.extend(lint(code))
    return ValidationReport(code=code, issues=issues, unknown_ids=sorted(set(visitor.unknown_ids)))
