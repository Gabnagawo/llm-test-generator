```python
import re

from playwright.sync_api import Page, expect


def test_opening_a_product_detail_page(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    
    page.get_by_test_id("item-0-title-link").click()
    expect(page).to_have_url(re.compile(r".*/inventory-item\.html\?id=0$"))
    
    expect(page.get_by_test_id("inventory-item-name")).first().to_have_text("Sauce Labs Bike Light")
    expect(page.get_by_test_id("inventory-item-price")).first().to_have_text("$9.99")
    
    page.get_by_test_id("back-to-products").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
```
