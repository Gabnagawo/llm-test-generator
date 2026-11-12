### system

You are a senior SDET. You write one Playwright end-to-end test in Python (pytest + pytest-playwright, sync API) for one user story.

Hard rules:
1. Output exactly one ```python code block and nothing else.
2. Imports allowed: `from playwright.sync_api import Page, expect`, `import re`, `import pytest`.
3. Define exactly one test function, named as requested, taking the `page: Page` fixture.
4. Navigate with relative paths only, e.g. page.goto("/"). The base URL is configured.
5. Locate elements with page.get_by_test_id("<id>") using ONLY ids from the page catalog. page.get_by_role / get_by_text / get_by_placeholder are allowed when no test id exists. Never invent test ids, CSS classes or XPath.
6. Assert every acceptance criterion with Playwright's web-first assertions: expect(locator).to_have_text(...), to_contain_text, to_be_visible, to_have_count, to_have_value, expect(page).to_have_url(re.compile(...)). Use expect(locator).not_to_be_visible() or to_have_count(0) for absent elements.
7. No sleeps: no time.sleep and no page.wait_for_timeout. Playwright waits automatically.
8. Each test starts in a fresh, logged-out browser context: perform the story's setup (including logging in) inside the test.
9. When several elements share a test id, narrow them with .first, .last, .nth(i) or .filter(has_text=...).

### user

Page catalog (captured from the live app):
App: saucedemo at https://www.saucedemo.com
Test id attribute: data-test (the fixture is configured so page.get_by_test_id("x") matches [data-test="x"])
Demo accounts (username / password): standard_user / secret_sauce, locked_out_user / secret_sauce, problem_user / secret_sauce, performance_glitch_user / secret_sauce, error_user / secret_sauce, visual_user / secret_sauce
Note: Every page except login requires a logged-in session; tests start from a fresh browser context, so log in first (page.goto('/') then fill username/password).
Note: The cart badge (shopping-cart-badge) is absent when the cart is empty.
Note: Product sort <select> values: az, za, lohi, hilo.
Note: Add/remove buttons are per product: add-to-cart-<slug> / remove-<slug>.
Note: Checkout step one requires first name, last name and postal code.
Note: The burger menu button has no data-test id: page.get_by_role("button", name="Open Menu").
Note: Product names and prices repeat per product; narrow with page.get_by_test_id("inventory-item").filter(has_text="...").

## page login: /  (logged out)
- "login-container" div
- "username" input type=text placeholder='Username'
- "password" input type=password placeholder='Password'
- "login-button" input type=submit text='Login'
- "login-credentials-container" div
- "login-credentials" div text='standard_user locked_out_user problem_user performance_glitch_user error_user vi'
- "login-password" div text='secret_sauce'

## page login_error: /  (after submitting an empty form)
- "error" h3 text='Epic sadface: Username is required'
- "error-button" button
- also present (described above): login-container, username, password, login-button, login-credentials-container, login-credentials, login-password

## page login_locked_out: /  (after logging in as locked_out_user)
- "error" h3 text='Epic sadface: Sorry, this user has been locked out.'
- also present (described above): login-container, username, password, error-button, login-button, login-credentials-container, login-credentials, login-password

## page login_wrong_password: /  (after logging in with a wrong password)
- "error" h3 text='Epic sadface: Username and password do not match any user in this service'
- also present (described above): login-container, username, password, error-button, login-button, login-credentials-container, login-credentials, login-password

## page inventory: /inventory.html  (logged in as standard_user, empty cart)
- "header-container" header
- "primary-header" div
- "open-menu" img
- "inventory-sidebar-link" a text='All Items'
- "dynamic-catalog-sidebar-link" a text='Dynamic Catalog'
- "about-sidebar-link" a text='About'
- "logout-sidebar-link" a text='Logout'
- "reset-sidebar-link" a text='Reset App State'
- "close-menu" img
- "shopping-cart-link" a
- "secondary-header" div
- "title" span text='Products'
- "active-option" span text='Name (A to Z)'
- "product-sort-container" select options=az,za,lohi,hilo
- "inventory-container" div
- "inventory-list" div
- "inventory-item" div x6 (use .first / .nth(i) / filter)
- "item-4-img-link" a
- "inventory-item-sauce-labs-backpack-img" img
- "inventory-item-description" div x6 (use .first / .nth(i) / filter)
- "item-4-title-link" a
- "inventory-item-name" div x6 (use .first / .nth(i) / filter) distinct texts in page order=["Sauce Labs Backpack", "Sauce Labs Bike Light", "Sauce Labs Bolt T-Shirt", "Sauce Labs Fleece Jacket", "Sauce Labs Onesie", "Test.allTheThings() T-Shirt (Red)"]
- "inventory-item-desc" div x6 (use .first / .nth(i) / filter) distinct texts in page order=["carry.allTheThings() with the sleek, streamlined Sly Pack that melds uncompromis", "A red light isn't the desired state in testing but it sure helps when riding you", "Get your testing superhero on with the Sauce Labs bolt T-shirt. From American Ap", "It's not every day that you come across a midweight quarter-zip fleece jacket ca", "Rib snap infant onesie for the junior automation engineer in development. Reinfo", "This classic Sauce Labs t-shirt is perfect to wear when cozying up to your keybo"]
- "inventory-item-price" div x6 (use .first / .nth(i) / filter) distinct texts in page order=["$29.99", "$9.99", "$15.99", "$49.99", "$7.99"]
- "add-to-cart-sauce-labs-backpack" button text='Add to cart'
- "item-0-img-link" a
- "inventory-item-sauce-labs-bike-light-img" img
- "item-0-title-link" a
- "add-to-cart-sauce-labs-bike-light" button text='Add to cart'
- "item-1-img-link" a
- "inventory-item-sauce-labs-bolt-t-shirt-img" img
- "item-1-title-link" a
- "add-to-cart-sauce-labs-bolt-t-shirt" button text='Add to cart'
- "item-5-img-link" a
- "inventory-item-sauce-labs-fleece-jacket-img" img
- "item-5-title-link" a
- "add-to-cart-sauce-labs-fleece-jacket" button text='Add to cart'
- "item-2-img-link" a
- "inventory-item-sauce-labs-onesie-img" img
- "item-2-title-link" a
- "add-to-cart-sauce-labs-onesie" button text='Add to cart'
- "item-3-img-link" a
- "inventory-item-test.allthethings()-t-shirt-(red)-img" img
- "item-3-title-link" a
- "add-to-cart-test.allthethings()-t-shirt-(red)" button text='Add to cart'
- "footer" footer
- "social-x" a text='X'
- "social-facebook" a text='Facebook'
- "social-linkedin" a text='LinkedIn'
- "footer-copy" div text='© 2026 Sauce Labs. All Rights Reserved. Terms of Service | Privacy Policy'

## page menu: /inventory.html  (inventory with the burger menu open)
- also present (described above): header-container, primary-header, open-menu, inventory-sidebar-link, dynamic-catalog-sidebar-link, about-sidebar-link, logout-sidebar-link, reset-sidebar-link, close-menu, shopping-cart-link, secondary-header, title, active-option, product-sort-container, inventory-container, inventory-list, inventory-item, item-4-img-link, inventory-item-sauce-labs-backpack-img, inventory-item-description, item-4-title-link, inventory-item-name, inventory-item-desc, inventory-item-price, add-to-cart-sauce-labs-backpack, item-0-img-link, inventory-item-sauce-labs-bike-light-img, item-0-title-link, add-to-cart-sauce-labs-bike-light, item-1-img-link, inventory-item-sauce-labs-bolt-t-shirt-img, item-1-title-link, add-to-cart-sauce-labs-bolt-t-shirt, item-5-img-link, inventory-item-sauce-labs-fleece-jacket-img, item-5-title-link, add-to-cart-sauce-labs-fleece-jacket, item-2-img-link, inventory-item-sauce-labs-onesie-img, item-2-title-link, add-to-cart-sauce-labs-onesie, item-3-img-link, inventory-item-test.allthethings()-t-shirt-(red)-img, item-3-title-link, add-to-cart-test.allthethings()-t-shirt-(red), footer, social-x, social-facebook, social-linkedin, footer-copy

## page inventory_full_cart: /inventory.html  (after adding all six products)
- "shopping-cart-badge" span text='6'
- "remove-sauce-labs-backpack" button text='Remove'
- "remove-sauce-labs-bike-light" button text='Remove'
- "remove-sauce-labs-bolt-t-shirt" button text='Remove'
- "remove-sauce-labs-fleece-jacket" button text='Remove'
- "remove-sauce-labs-onesie" button text='Remove'
- "remove-test.allthethings()-t-shirt-(red)" button text='Remove'
- also present (described above): header-container, primary-header, open-menu, inventory-sidebar-link, dynamic-catalog-sidebar-link, about-sidebar-link, logout-sidebar-link, reset-sidebar-link, close-menu, shopping-cart-link, secondary-header, title, active-option, product-sort-container, inventory-container, inventory-list, inventory-item, item-4-img-link, inventory-item-sauce-labs-backpack-img, inventory-item-description, item-4-title-link, inventory-item-name, inventory-item-desc, inventory-item-price, item-0-img-link, inventory-item-sauce-labs-bike-light-img, item-0-title-link, item-1-img-link, inventory-item-sauce-labs-bolt-t-shirt-img, item-1-title-link, item-5-img-link, inventory-item-sauce-labs-fleece-jacket-img, item-5-title-link, item-2-img-link, inventory-item-sauce-labs-onesie-img, item-2-title-link, item-3-img-link, inventory-item-test.allthethings()-t-shirt-(red)-img, item-3-title-link, footer, social-x, social-facebook, social-linkedin, footer-copy

## page cart_full: /cart.html  (cart with all six products)
- "title" span text='Your Cart'
- "cart-contents-container" div
- "cart-list" div
- "cart-quantity-label" div text='QTY'
- "cart-desc-label" div text='Description'
- "item-quantity" div x6 (use .first / .nth(i) / filter) text='1'
- "continue-shopping" button text='Continue Shopping'
- "checkout" button text='Checkout'
- also present (described above): header-container, primary-header, open-menu, inventory-sidebar-link, dynamic-catalog-sidebar-link, about-sidebar-link, logout-sidebar-link, reset-sidebar-link, close-menu, shopping-cart-link, shopping-cart-badge, secondary-header, inventory-item, item-4-title-link, inventory-item-name, inventory-item-desc, inventory-item-price, remove-sauce-labs-backpack, item-0-title-link, remove-sauce-labs-bike-light, item-1-title-link, remove-sauce-labs-bolt-t-shirt, item-5-title-link, remove-sauce-labs-fleece-jacket, item-2-title-link, remove-sauce-labs-onesie, item-3-title-link, remove-test.allthethings()-t-shirt-(red), footer, social-x, social-facebook, social-linkedin, footer-copy

## page inventory_item: /inventory-item.html?id=0  (detail page of a product that is not in the cart)
- "shopping-cart-badge" span text='1'
- "back-to-products" button text='Back to products'
- "item-sauce-labs-bike-light-img" img
- "inventory-item-name" div text='Sauce Labs Bike Light'
- "inventory-item-desc" div text="A red light isn't the desired state in testing but it sure helps when riding you"
- "inventory-item-price" div text='$9.99'
- "add-to-cart" button text='Add to cart'
- also present (described above): header-container, primary-header, open-menu, inventory-sidebar-link, dynamic-catalog-sidebar-link, about-sidebar-link, logout-sidebar-link, reset-sidebar-link, close-menu, shopping-cart-link, secondary-header, inventory-container, inventory-item, footer, social-x, social-facebook, social-linkedin, footer-copy

## page inventory_item_in_cart: /inventory-item.html?id=4  (detail page of the backpack, which is in the cart)
- "item-sauce-labs-backpack-img" img
- "inventory-item-name" div text='Sauce Labs Backpack'
- "inventory-item-desc" div text='carry.allTheThings() with the sleek, streamlined Sly Pack that melds uncompromis'
- "inventory-item-price" div text='$29.99'
- "remove" button text='Remove'
- also present (described above): header-container, primary-header, open-menu, inventory-sidebar-link, dynamic-catalog-sidebar-link, about-sidebar-link, logout-sidebar-link, reset-sidebar-link, close-menu, shopping-cart-link, shopping-cart-badge, secondary-header, back-to-products, inventory-container, inventory-item, footer, social-x, social-facebook, social-linkedin, footer-copy

## page cart: /cart.html  (cart with the backpack only)
- also present (described above): header-container, primary-header, open-menu, inventory-sidebar-link, dynamic-catalog-sidebar-link, about-sidebar-link, logout-sidebar-link, reset-sidebar-link, close-menu, shopping-cart-link, shopping-cart-badge, secondary-header, title, cart-contents-container, cart-list, cart-quantity-label, cart-desc-label, inventory-item, item-quantity, item-4-title-link, inventory-item-name, inventory-item-desc, inventory-item-price, remove-sauce-labs-backpack, continue-shopping, checkout, footer, social-x, social-facebook, social-linkedin, footer-copy

## page checkout_step_one: /checkout-step-one.html  (checkout information form)
- "title" span text='Checkout: Your Information'
- "checkout-info-container" div
- "firstName" input type=text placeholder='First Name'
- "lastName" input type=text placeholder='Last Name'
- "postalCode" input type=text placeholder='Zip/Postal Code'
- "cancel" button text='Cancel'
- "continue" input type=submit text='Continue'
- also present (described above): header-container, primary-header, open-menu, inventory-sidebar-link, dynamic-catalog-sidebar-link, about-sidebar-link, logout-sidebar-link, reset-sidebar-link, close-menu, shopping-cart-link, shopping-cart-badge, secondary-header, footer, social-x, social-facebook, social-linkedin, footer-copy

## page checkout_step_one_error: /checkout-step-one.html  (after continuing with an empty form)
- "error" h3 text='Error: First Name is required'
- also present (described above): header-container, primary-header, open-menu, inventory-sidebar-link, dynamic-catalog-sidebar-link, about-sidebar-link, logout-sidebar-link, reset-sidebar-link, close-menu, shopping-cart-link, shopping-cart-badge, secondary-header, title, checkout-info-container, firstName, lastName, postalCode, error-button, cancel, continue, footer, social-x, social-facebook, social-linkedin, footer-copy

## page checkout_step_two: /checkout-step-two.html  (order overview)
- "title" span text='Checkout: Overview'
- "checkout-summary-container" div
- "payment-info-label" div text='Payment Information:'
- "payment-info-value" div text='SauceCard #31337'
- "shipping-info-label" div text='Shipping Information:'
- "shipping-info-value" div text='Free Pony Express Delivery!'
- "total-info-label" div text='Price Total'
- "subtotal-label" div text='Item total: $29.99'
- "tax-label" div text='Tax: $2.40'
- "total-label" div text='Total: $32.39'
- "finish" button text='Finish'
- also present (described above): header-container, primary-header, open-menu, inventory-sidebar-link, dynamic-catalog-sidebar-link, about-sidebar-link, logout-sidebar-link, reset-sidebar-link, close-menu, shopping-cart-link, shopping-cart-badge, secondary-header, cart-list, cart-quantity-label, cart-desc-label, inventory-item, item-quantity, item-4-title-link, inventory-item-name, inventory-item-desc, inventory-item-price, cancel, footer, social-x, social-facebook, social-linkedin, footer-copy

## page checkout_complete: /checkout-complete.html  (after finishing the order)
- "title" span text='Checkout: Complete!'
- "checkout-complete-container" div
- "pony-express" img
- "complete-header" h2 text='Thank you for your order!'
- "complete-text" div text='Your order has been dispatched, and will arrive just as fast as the pony can get'
- "back-to-products" button text='Back Home'
- "generate-pdf-order" button text='Generate PDF order'
- also present (described above): header-container, primary-header, open-menu, inventory-sidebar-link, dynamic-catalog-sidebar-link, about-sidebar-link, logout-sidebar-link, reset-sidebar-link, close-menu, shopping-cart-link, secondary-header, footer, social-x, social-facebook, social-linkedin, footer-copy

Format example (a different story):
```python
import re

from playwright.sync_api import Page, expect


def test_footer_shows_social_links(page: Page) -> None:
    # Deliberately not one of the benchmark stories: it only shows the expected shape.
    page.goto("/")
    page.get_by_test_id("username").fill("visual_user")
    page.get_by_test_id("password").fill("secret_sauce")
    page.get_by_test_id("login-button").click()
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))
    expect(page.get_by_test_id("social-linkedin")).to_be_visible()
    expect(page.get_by_test_id("footer-copy")).to_contain_text("Sauce Labs")
```

Write the test function `test_successful_login` for this story:
Title: Successful login
Narrative: As a registered shopper, I want to log in with my username and password so that I can browse the products.
Acceptance criteria:
- Given I am on the login page
- When I log in as "standard_user" with password "secret_sauce"
- Then I am taken to the inventory page (URL ends with /inventory.html)
- And the page title reads "Products"
- And exactly 6 products are listed
