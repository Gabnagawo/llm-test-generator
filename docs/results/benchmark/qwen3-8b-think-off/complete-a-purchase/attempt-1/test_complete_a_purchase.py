import re

from playwright.sync_api import Page, expect


def test_complete_a_purchase(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))

    page.get_by_test_id("add-to-cart-sauce-labs-backpack").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    expect(page.get_by_test_id("shopping-cart-badge")).to_have_text("1")

    page.get_by_test_id("shopping-cart-link").click()
    expect(page).to_have_url(re.compile(r".*/cart\.html$"))

    page.get_by_test_id("checkout").click()
    expect(page).to_have_url(re.compile(r".*/checkout-step-one\.html$"))

    page.get_by_test_id("firstName").fill("Ada")
    page.get_by_test_id("lastName").fill("Lovelace")
    page.get_by_test_id("postalCode").fill("12345")
    page.get_by_test_id("continue").click()
    expect(page).to_have_url(re.compile(r".*/checkout-step-two\.html$"))

    expect(page.get_by_test_id("subtotal-label")).to_have_text("Item total: $29.99")
    expect(page.get_by_test_id("total-label")).to_have_text("Total: $32.39")

    page.get_by_test_id("finish").click()
    expect(page).to_have_url(re.compile(r".*/checkout-complete\.html$"))

    expect(page.get_by_test_id("complete-header")).to_have_text("Thank you for your order!")
