```python
import re

from playwright.sync_api import Page, expect


def test_sorting_by_price_from_low_to_high(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    
    page.get_by_test_id("product-sort-container").select_option("lohi")
    
    expect(page.get_by_test_id("inventory-item-price").nth(0)).to_have_text("$7.99")
    expect(page.get_by_test_id("inventory-item-price").last).to_have_text("$49.99")
```
