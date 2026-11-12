import re

from playwright.sync_api import Page, expect


def test_logout_from_the_menu(page: Page) -> None:
    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    
    page.get_by_role("button", name="Open Menu").click()
    page.get_by_test_id("logout-sidebar-link").click()
    expect(page).to_have_url(re.compile(r".*/login\.html$"))
    expect(page.get_by_test_id("login-button")).to_be_visible()
