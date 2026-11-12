```python
import re

from playwright.sync_api import Page, expect


def test_wrong_password_is_rejected(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("not_the_password")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/$"))
    expect(page.get_by_test_id("error")).to_have_text("Epic sadface: Username and password do not match any user in this service")
    expect(page.get_by_test_id("username")).to_be_visible()
    expect(page.get_by_test_id("password")).to_be_visible()
```
