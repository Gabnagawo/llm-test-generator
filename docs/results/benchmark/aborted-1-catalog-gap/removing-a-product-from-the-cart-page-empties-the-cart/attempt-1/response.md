```python
import re

from playwright.sync_api import Page, expect


def test_removing_a_product_from_the_cart_page_empties_the_cart(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    
    page.get_by_test_id("add-to-cart-sauce-labs-bike-light").click()
    expect(page.get_by_test_id("shopping-cart-badge")).to_have_text("1")
    
    page.get_by_test_id("shopping-cart-link").click()
    expect(page).to_have_url(re.compile(r".*/cart\.html$"))
    
    page.get_by_test_id("remove-sauce-labs-bike-light").click()
    expect(page.get_by_test_id("shopping-cart-badge")).not_to_be_visible()
    expect(page.get_by_test_id("cart-list")).to_have_count(0)
```
