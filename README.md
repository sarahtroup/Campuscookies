# Campus Cookies

GitHub Pages serves the storefront and its email preorder flow. To turn on
shared inventory and receive preorders through the website, host the storefront
with the included Python 3.11+ service and use a persistent SQLite database
outside the website directory. Set up HTTPS at the hosting layer.

```sh
python inventory.py --db /path/to/private/cookies.sqlite serve
```

The service starts each eligible Friday with 125 cookies per flavor and enforces
the Monday 2 p.m. Eastern cutoff. A separate capacity of 100 Roommate tins is
configured for each Friday. The Roommate remains sold out on the storefront
until its checkout is enabled. These capacities are for the Python service.
GitHub Pages uses email preorders. It stores preorder requests and reserves the
requested quantities together. It does not send email or collect payments.
Bakery staff can review requests and follow up using the recorded email address.

```sh
python inventory.py --db /path/to/private/cookies.sqlite set-limit 2027-01-08 valedictorian 120
python inventory.py --db /path/to/private/cookies.sqlite orders 2027-01-08
python inventory.py --db /path/to/private/cookies.sqlite cancel ORDER_ID
```

The database contains customer contact information. Keep the file and backups
private. Cancelling an order releases its inventory for the pickup date.

## Square checkout

Run the storefront on a single HTTPS-backed Python host with a persistent private
SQLite database. Configure `SQUARE_ACCESS_TOKEN` and `SQUARE_LOCATION_ID` in the
host's private environment. Keep Sandbox and production credentials and databases
separate. Use the Campus Cookies pickup location in Square.

```sh
python inventory.py --db /path/to/private/cookies.sqlite serve --square sandbox
```

The existing box builder sends customers to Square-hosted checkout. Square
receives the flavors, quantities, gift box, pickup date and pickup contact.
Paid orders can be managed in Square Orders. Square checkout mode accepts orders
until 9:30 a.m. Eastern on the Friday before pickup, without per-flavor stock
limits. Customers have 30 minutes to complete checkout. Run the service
continuously so abandoned checkout links can be canceled.

Before deploying with `--square production`, validate a payment in Sandbox and
verify the pickup details in Square Orders. Confirm the Square location and the
sales tax treatment for Campus Cookies before accepting live orders. The
integration charges the order total shown on the existing storefront.

## Update the announcement

In GitHub, open `index.html` and select the pencil icon. Search for
`id="announcement-message"` and replace the text between the opening and
closing paragraph tags. Commit the change to `main` to publish it. To hide the
banner, add `hidden` to its opening `<aside>` tag. Remove `hidden` to show it again.
