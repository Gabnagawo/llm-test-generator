from __future__ import annotations

from pathlib import Path

import pytest

from llm_test_generator.catalog import Catalog, load_catalog
from llm_test_generator.models import Story, StoryFormat

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://www.saucedemo.com"

GOOD_TEST = """\
import re

from playwright.sync_api import Page, expect


def test_successful_login(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\\.html$"))
    expect(page.get_by_test_id("inventory-item")).to_have_count(6)
"""


def fenced(code: str, lead: str = "Here is the test:") -> str:
    return f"{lead}\n\n```python\n{code}```\n"


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return load_catalog()


@pytest.fixture
def story() -> Story:
    return Story(
        id="successful-login",
        title="Successful login",
        narrative="As a shopper I want to log in.",
        criteria=["Given I am on the login page", "Then I see 6 products"],
        source="tests",
        format=StoryFormat.MARKDOWN,
        tags=["smoke"],
    )
