# Campus Cookies

GitHub Pages serves the storefront and its email preorder flow. To turn on
shared inventory and receive preorders through the website, host the storefront
with the included Python 3.11+ service and use a persistent SQLite database
outside the website directory. Set up HTTPS at the hosting layer.

```sh
python inventory.py --db /path/to/private/cookies.sqlite serve
```

The service starts each eligible Friday with 100 cookies per flavor and enforces
the Monday 2 p.m. Eastern cutoff. It stores preorder requests and reserves the
requested quantities together. It does not send email or collect payments.
Bakery staff can review requests and follow up using the recorded email address.

```sh
python inventory.py --db /path/to/private/cookies.sqlite set-limit 2027-01-08 valedictorian 120
python inventory.py --db /path/to/private/cookies.sqlite orders 2027-01-08
python inventory.py --db /path/to/private/cookies.sqlite cancel ORDER_ID
```

The database contains customer contact information. Keep the file and backups
private. Cancelling an order releases its inventory for the pickup date.
