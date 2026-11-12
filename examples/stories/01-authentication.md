# Authentication stories for the Swag Labs demo shop (saucedemo.com)

## Successful login
Tags: @smoke @auth
As a registered shopper, I want to log in with my username and password so that I can browse the products.

### Acceptance criteria
- Given I am on the login page
- When I log in as "standard_user" with password "secret_sauce"
- Then I am taken to the inventory page (URL ends with /inventory.html)
- And the page title reads "Products"
- And exactly 6 products are listed

## Locked-out user is rejected
Tags: @auth @negative
As the shop owner, I want locked accounts to be refused so that blocked users cannot place orders.

### Acceptance criteria
- Given I am on the login page
- When I log in as "locked_out_user" with password "secret_sauce"
- Then I stay on the login page
- And an error message says "Epic sadface: Sorry, this user has been locked out."

## Wrong password is rejected
Tags: @auth @negative
As a shopper, I want a clear message when my credentials are wrong so that I know to retry.

### Acceptance criteria
- Given I am on the login page
- When I log in as "standard_user" with password "not_the_password"
- Then an error message says "Epic sadface: Username and password do not match any user in this service"
- And the username and password fields are still visible

## Logout from the menu
Tags: @auth
As a logged-in shopper, I want to log out so that the next person on this computer cannot use my session.

### Acceptance criteria
- Given I am logged in as "standard_user"
- When I open the menu and choose "Logout"
- Then I am back on the login page
- And the login button is visible
