import re

from playwright.sync_api import Page, expect


def test_checkout_requires_a_first_name(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    
    page.get_by_test_id("add-to-cart-sauce-labs-onesie").click()
    page.get_by_test_id("shopping-cart-link").click()
    page.get_by_test_id("checkout").click()
    
    expect(page).to_have_url(re.compile(r".*/checkout-step-one\.html$"))
    page.get_by_test_id("continue").click()
    
    expect(page).to_have_url(re.compile(r".*/checkout-step-one\.html$"))
    expect(page.get_by_test_id("error")).to_have_text("Error: First Name is required")
