@cart
Feature: Shopping cart
  As a shopper I want to collect products in a cart before checking out.

  Background:
    Given I am logged in as "standard_user" with password "secret_sauce"

  @smoke
  Scenario: Adding a product updates the cart badge
    When I add "Sauce Labs Backpack" to the cart from the inventory page
    Then the cart badge shows "1"
    And the backpack's button now reads "Remove"

  Scenario: Removing a product from the cart page empties the cart
    Given I have added "Sauce Labs Bike Light" to the cart
    When I open the cart
    And I remove "Sauce Labs Bike Light"
    Then the cart contains no items
    And the cart badge is not displayed

  Scenario: The cart lists every product that was added
    When I add "Sauce Labs Backpack" and "Sauce Labs Onesie" to the cart
    And I open the cart
    Then the cart lists exactly 2 items
    And the cart shows "Sauce Labs Backpack" and "Sauce Labs Onesie"
