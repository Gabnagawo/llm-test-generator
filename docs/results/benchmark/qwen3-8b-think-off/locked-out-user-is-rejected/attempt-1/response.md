```python
import re

from playwright.sync_api import Page, expect


def test_locked_out_user_is_rejected(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("locked_out_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/$"))
    expect(page.get_by_test_id("error")).to_have_text("Epic sadface: Sorry, this user has been locked out.")
```
