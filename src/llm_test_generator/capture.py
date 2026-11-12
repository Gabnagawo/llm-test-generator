"""Capture the page catalog from the live demo app with Playwright.

``ltg catalog capture`` drives saucedemo.com through every page a story can reach
(login, inventory, item, menu, cart, the three checkout steps and the error states)
and records each element that carries a ``data-test`` attribute. The result is
committed, so generation is reproducible and the validator has a closed set of ids.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from importlib import metadata
from typing import Any

from llm_test_generator.catalog import Catalog, Element, Page

# Runs in the browser: one row per element with a data-test attribute, in DOM order.
ELEMENTS_JS = """
(attr) => Array.from(document.querySelectorAll(`[${attr}]`)).map((el) => ({
  test_id: el.getAttribute(attr),
  tag: el.tagName.toLowerCase(),
  // Leaves and buttons: their visible text. Containers: only their own text nodes,
  // so an error <h3> with a close button inside still yields its message.
  text: (el.children.length === 0 || el.tagName === 'BUTTON')
    ? (el.innerText || (el.type === 'submit' ? el.value : '') || '')
    : Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent).join(' '),
  input_type: el.tagName === 'INPUT' ? el.getAttribute('type') : null,
  placeholder: el.getAttribute('placeholder'),
  options: el.tagName === 'SELECT' ? Array.from(el.options).map((o) => o.value) : [],
  visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
}))
"""

SAUCEDEMO_CREDENTIALS = {
    "standard_user": "secret_sauce",
    "locked_out_user": "secret_sauce",
    "problem_user": "secret_sauce",
    "performance_glitch_user": "secret_sauce",
    "error_user": "secret_sauce",
    "visual_user": "secret_sauce",
}

SAUCEDEMO_NOTES = [
    "Every page except login requires a logged-in session; tests start from a fresh "
    "browser context, so log in first (page.goto('/') then fill username/password).",
    "The cart badge (shopping-cart-badge) is absent when the cart is empty.",
    "Product sort <select> values: az, za, lohi, hilo.",
    "Add/remove buttons are per product: add-to-cart-<slug> / remove-<slug>.",
    "Checkout step one requires first name, last name and postal code.",
    'The burger menu button has no data-test id: page.get_by_role("button", name="Open Menu").',
    "Product names and prices repeat per product; narrow with "
    'page.get_by_test_id("inventory-item").filter(has_text="...").',
]

TEXT_LIMIT = 80
MAX_SAMPLES = 8


def normalize_elements(
    rows: Iterable[Mapping[str, Any]], max_text: int = TEXT_LIMIT
) -> list[Element]:
    """Merge raw DOM rows into catalog elements: one per test id, with a count.

    Rows for invisible elements are kept (a closed menu is still addressable once
    opened) but text is taken from the first row that has any.
    """
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        test_id = str(row.get("test_id") or "").strip()
        if not test_id:
            continue
        text = " ".join(str(row.get("text") or "").split())[:max_text]
        entry = merged.get(test_id)
        if entry is None:
            merged[test_id] = {
                "test_id": test_id,
                "tag": str(row.get("tag") or "?"),
                "count": 1,
                "text": text,
                "input_type": row.get("input_type") or None,
                "placeholder": row.get("placeholder") or None,
                "options": [str(o) for o in row.get("options") or []],
                "samples": [text] if text else [],
            }
        else:
            entry["count"] += 1
            # Repeated elements (product names, prices) differ per row: keep the distinct
            # values in DOM order, which is also what sorting tests assert on.
            if text and text not in entry["samples"] and len(entry["samples"]) < MAX_SAMPLES:
                entry["samples"].append(text)
    elements = []
    for entry in merged.values():
        samples = entry.pop("samples")
        elements.append(Element(**entry, samples=samples if entry["count"] > 1 else []))
    return elements


def _snapshot(page: Any, name: str, state: str, attr: str) -> Page:
    rows = page.evaluate(ELEMENTS_JS, attr)
    path = page.url.split("saucedemo.com", 1)[-1] or "/"
    return Page(
        name=name,
        path=path,
        state=state,
        title=page.title(),
        elements=normalize_elements(rows),
    )


def _saucedemo_tour(page: Any, snap: Callable[[str, str, str], None]) -> None:  # pragma: no cover
    """Visit every reachable state. Exercised by ``tests/e2e/test_capture_live.py``."""
    page.goto("/")
    snap("login", "logged out", "login-button")
    page.get_by_test_id("login-button").click()
    snap("login_error", "after submitting an empty form", "error")
    page.get_by_test_id("username").fill("locked_out_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    snap("login_locked_out", "after logging in as locked_out_user", "error")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("wrong_password")
    page.get_by_test_id("login-button").click()
    snap("login_wrong_password", "after logging in with a wrong password", "error")

    page.goto("/")
    page.get_by_test_id("username").fill("standard_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    page.wait_for_url("**/inventory.html")
    snap("inventory", "logged in as standard_user, empty cart", "inventory-list")

    page.get_by_role("button", name="Open Menu").click()
    page.get_by_test_id("logout-sidebar-link").wait_for(state="visible")
    snap("menu", "inventory with the burger menu open", "logout-sidebar-link")
    page.get_by_role("button", name="Close Menu").click()

    page.get_by_test_id("add-to-cart-sauce-labs-backpack").click()
    snap("inventory_with_cart", "after adding the backpack", "shopping-cart-badge")

    page.get_by_test_id("inventory-item-name").first.click()
    page.wait_for_url("**/inventory-item.html*")
    snap("inventory_item", "detail page opened from the first product name", "back-to-products")

    page.get_by_test_id("shopping-cart-link").click()
    page.wait_for_url("**/cart.html")
    snap("cart", "cart with the backpack", "checkout")

    page.get_by_test_id("checkout").click()
    page.wait_for_url("**/checkout-step-one.html")
    snap("checkout_step_one", "checkout information form", "firstName")
    page.get_by_test_id("continue").click()
    snap("checkout_step_one_error", "after continuing with an empty form", "error")

    page.get_by_test_id("firstName").fill("Ada")
    page.get_by_test_id("lastName").fill("Lovelace")
    page.get_by_test_id("postalCode").fill("12345")
    page.get_by_test_id("continue").click()
    page.wait_for_url("**/checkout-step-two.html")
    snap("checkout_step_two", "order overview", "finish")

    page.get_by_test_id("finish").click()
    page.wait_for_url("**/checkout-complete.html")
    snap("checkout_complete", "after finishing the order", "complete-header")


def capture_catalog(
    base_url: str = "https://www.saucedemo.com", headless: bool = True
) -> Catalog:  # pragma: no cover - needs a browser and network; see tests/e2e
    from playwright.sync_api import sync_playwright

    attr = "data-test"
    pages: list[Page] = []
    with sync_playwright() as pw:
        pw.selectors.set_test_id_attribute(attr)
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(base_url=base_url)
        page = context.new_page()

        def snap(name: str, state: str, ready: str) -> None:
            # SPA routes change the URL before rendering; wait for a page-specific element.
            page.get_by_test_id(ready).first.wait_for(state="visible")
            pages.append(_snapshot(page, name, state, attr))

        try:
            _saucedemo_tour(page, snap)
        finally:
            context.close()
            browser.close()

    return Catalog(
        app="saucedemo",
        base_url=base_url,
        captured_at=datetime.now(UTC).replace(microsecond=0),
        captured_with=f"playwright {metadata.version('playwright')} chromium headless",
        test_id_attribute=attr,
        credentials=SAUCEDEMO_CREDENTIALS,
        notes=SAUCEDEMO_NOTES,
        pages=pages,
    )
