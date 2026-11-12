@catalog
Feature: Product catalog
  As a shopper I want to sort and inspect products so that I find what I need quickly.

  Background:
    Given I am logged in as "standard_user" with password "secret_sauce"

  Scenario: Sorting by price from low to high
    When I sort the products by "Price (low to high)"
    Then the first product price is "$7.99"
    And the last product price is "$49.99"

  Scenario: Sorting by name from Z to A
    When I sort the products by "Name (Z to A)"
    Then the first product is "Test.allTheThings() T-Shirt (Red)"
    And the last product is "Sauce Labs Backpack"

  Scenario: Opening a product detail page
    When I click the product name "Sauce Labs Bike Light"
    Then the detail page shows the name "Sauce Labs Bike Light"
    And the detail page shows the price "$9.99"
    When I click "Back to products"
    Then I am on the inventory page again
