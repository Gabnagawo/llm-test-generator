```python
import re

from playwright.sync_api import Page, expect


def test_adding_a_product_updates_the_cart_badge(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    page.get_by_test_id("add-to-cart-sauce-labs-backpack").click()
    expect(page.get_by_test_id("shopping-cart-badge")).to_have_text("1")
    expect(page.get_by_test_id("add-to-cart-sauce-labs-backpack")).to_have_text("Remove")
```
