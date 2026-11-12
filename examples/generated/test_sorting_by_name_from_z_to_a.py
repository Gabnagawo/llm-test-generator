import re

from playwright.sync_api import Page, expect


def test_sorting_by_name_from_z_to_a(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    
    page.get_by_test_id("product-sort-container").select_option("za")
    
    expect(page.get_by_test_id("inventory-item-name").filter(has_text="Test.allTheThings() T-Shirt (Red)")).to_be_visible()
    expect(page.get_by_test_id("inventory-item-name").last).to_have_text("Sauce Labs Backpack")
