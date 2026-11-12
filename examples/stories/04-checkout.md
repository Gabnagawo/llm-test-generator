# Checkout stories

## Complete a purchase
Tags: @smoke @checkout
As a shopper, I want to pay for the products in my cart so that they are shipped to me.

### Acceptance criteria
- Given I am logged in as "standard_user" with password "secret_sauce"
- And I have added "Sauce Labs Backpack" to the cart
- When I go to the cart and click "Checkout"
- And I enter first name "Ada", last name "Lovelace" and postal code "12345" and continue
- Then the overview shows "Item total: $29.99" and "Total: $32.39"
- When I click "Finish"
- Then I see the heading "Thank you for your order!"

## Checkout requires a first name
Tags: @checkout @negative
As the shop owner, I want shipping details to be complete so that orders can be delivered.

### Acceptance criteria
- Given I am logged in as "standard_user" with password "secret_sauce"
- And I have added "Sauce Labs Onesie" to the cart
- When I start the checkout and continue without entering a first name
- Then an error message says "Error: First Name is required"
- And I am still on the checkout information page
