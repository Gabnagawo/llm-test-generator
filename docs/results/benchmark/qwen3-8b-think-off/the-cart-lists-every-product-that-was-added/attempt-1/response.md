```python
import re

from playwright.sync_api import Page, expect


def test_the_cart_lists_every_product_that_was_added(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    
    page.get_by_test_id("add-to-cart-sauce-labs-backpack").click()
    page.get_by_test_id("add-to-cart-sauce-labs-onesie").click()
    
    page.get_by_test_id("shopping-cart-link").click()
    expect(page).to_have_url(re.compile(r".*/cart\.html$"))
    
    cart_items = page.get_by_test_id("cart-list").get_by_test_id("inventory-item")
    expect(cart_items).to_have_count(2)
    expect(cart_items.nth(0)).to_have_text("Sauce Labs Backpack")
    expect(cart_items.nth(1)).to_have_text("Sauce Labs Onesie")
```
