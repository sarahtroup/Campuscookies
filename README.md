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

## Square checkout on GitHub Pages

Deploy `square-checkout.mjs` as a Cloudflare Worker module. Add the Square access
token as a Worker secret named `SQUARE_ACCESS_TOKEN` and configure
`SQUARE_LOCATION_ID` for the Campus Cookies pickup location. Sandbox is the
default. Use a separate Worker and its own secrets for production and set
`SQUARE_ENV=production` on that Worker.

In the storefront document head, point to the Worker’s checkout endpoint.

```html
<meta name="campus-square-checkout" content="https://YOUR-WORKER.workers.dev/checkout">
```

The Worker accepts calls from the existing GitHub Pages origin, prices the box
server-side, and checks the 9:30 a.m. Eastern cutoff the Friday before pickup
before creating a single-use Square payment link. The cutoff applies to link
creation. A previously issued link can still be opened after the cutoff. This
checkout path has no cookie inventory quotas and requires no database. Confirm
the Square location, the total, pickup details in Square Orders, and sales tax
treatment before switching to production.

## Update the announcement

In GitHub, open `index.html` and select the pencil icon. Search for
`id="announcement-message"` and replace the text between the opening and
closing paragraph tags. Commit the change to `main` to publish it. To hide the
banner, add `hidden` to its opening `<aside>` tag. Remove `hidden` to show it again.
