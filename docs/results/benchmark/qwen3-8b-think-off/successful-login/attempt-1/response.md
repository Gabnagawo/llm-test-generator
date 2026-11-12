```python
import re

from playwright.sync_api import Page, expect


def test_successful_login(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    expect(page.get_by_test_id("title")).to_have_text("Products")
    expect(page.get_by_test_id("inventory-item")).to_have_count(6)
```
