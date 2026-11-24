"""Campus Cookies order and inventory service, using a persistent SQLite file."""
import argparse
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
FLAVORS = ("valedictorian", "all-nighter", "party-animal", "overachiever", "nutty-professor")
BOX_SIZES = {6, 12, 24, 36, 48}
DEFAULT_LIMIT = 100
FIRST_PICKUP = date(2027, 1, 1)
EASTERN = ZoneInfo("America/New_York")
SCHEMA = """
CREATE TABLE IF NOT EXISTS limits (
  pickup TEXT NOT NULL, flavor TEXT NOT NULL, capacity INTEGER NOT NULL,
  PRIMARY KEY (pickup, flavor)
);
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY, pickup TEXT NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL,
  gift INTEGER NOT NULL, total_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS quantities (
  order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  flavor TEXT NOT NULL, quantity INTEGER NOT NULL,
  PRIMARY KEY (order_id, flavor)
);
"""


class SoldOut(ValueError):
    pass


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def pickup_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Choose a Friday pickup date.")
    day = date.fromisoformat(value)
    if day < FIRST_PICKUP or day.weekday() != 4:
        raise ValueError("Choose a Friday pickup date starting in January 2027.")
    return day


def require_open(value, now=None):
    day = pickup_day(value)
    cutoff = datetime.combine(day - timedelta(days=4), datetime.min.time(), EASTERN).replace(hour=14)
    if (now or datetime.now(EASTERN)) >= cutoff:
        raise ValueError("The preorder deadline has passed for this Friday.")


def availability(db, pickup):
    limits = dict(db.execute("SELECT flavor, capacity FROM limits WHERE pickup = ?", (pickup,)))
    used = dict(db.execute(
        "SELECT flavor, SUM(quantity) FROM quantities JOIN orders ON orders.id = quantities.order_id "
        "WHERE pickup = ? GROUP BY flavor", (pickup,)
    ))
    return {flavor: max(0, limits.get(flavor, DEFAULT_LIMIT) - used.get(flavor, 0)) for flavor in FLAVORS}


def reserve(db, payload, now=None):
    if not isinstance(payload, dict):
        raise ValueError("Invalid order.")
    pickup = payload.get("pickup")
    quantities = payload.get("quantities")
    gift = payload.get("gift")
    name = payload.get("name")
    email = payload.get("email")
    order_id = payload.get("id")
    if not isinstance(order_id, str) or not re.fullmatch(r"[a-f0-9]{32}", order_id):
        raise ValueError("Invalid order reference.")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError("Enter a name for pickup.")
    if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Enter a valid email address.")
    if type(gift) is not bool or not isinstance(quantities, dict) or set(quantities) != set(FLAVORS):
        raise ValueError("Review your cookie selection.")
    if any(type(n) is not int or not 0 <= n <= 48 for n in quantities.values()):
        raise ValueError("Enter whole cookie quantities.")
    count = sum(quantities.values())
    total = count * 350 + (500 if gift else 0)
    with db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if previous:
            saved = dict(db.execute("SELECT flavor, quantity FROM quantities WHERE order_id = ?", (order_id,)))
            if (previous["pickup"], previous["name"], previous["email"], previous["gift"], saved) != (
                pickup, name.strip(), email, int(gift), quantities
            ):
                raise ValueError("This order reference is already in use.")
            return {"id": order_id, "totalCents": previous["total_cents"]}
        if count not in BOX_SIZES:
            raise ValueError("Fill a box of 6, 12, 24, 36, or 48 cookies.")
        require_open(pickup, now)
        stock = availability(db, pickup)
        if any(qty > stock[flavor] for flavor, qty in quantities.items()):
            raise SoldOut("Some flavors have sold out or have fewer cookies available. Review your box.")
        db.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", (order_id, pickup, name.strip(), email, gift, total))
        db.executemany("INSERT INTO quantities VALUES (?, ?, ?)", ((order_id, flavor, qty) for flavor, qty in quantities.items()))
    return {"id": order_id, "totalCents": total}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def json(self, status, payload):
        self.respond(status, json.dumps(payload).encode())

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path in ("/", "/index.html"):
            html = (ROOT / "index.html").read_text().replace(
                '<meta charset="utf-8">', '<meta charset="utf-8"><meta name="campus-inventory" content="enabled">'
            )
            self.respond(200, html.encode(), "text/html; charset=utf-8")
        elif url.path == "/api/availability":
            pickup = parse_qs(url.query).get("pickup", [""])[0]
            try:
                require_open(pickup)
            except ValueError as error:
                self.json(400, {"error": str(error)})
                return
            with closing(connect(self.server.database)) as db:
                self.json(200, availability(db, pickup))
        elif re.fullmatch(r"/assets/[a-z0-9-]+\.(png|webp)", url.path):
            asset = ROOT / url.path.lstrip("/")
            if asset.is_file():
                self.respond(200, asset.read_bytes(), f"image/{asset.suffix[1:]}")
            else:
                self.json(404, {"error": "File not found."})
        else:
            self.json(404, {"error": "Page not found."})

    def do_POST(self):
        if self.path != "/api/orders":
            self.json(404, {"error": "Page not found."})
            return
        if self.headers.get_content_type() != "application/json":
            self.json(415, {"error": "Send orders as JSON."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid order.")
            payload = json.loads(self.rfile.read(length))
            with closing(connect(self.server.database)) as db:
                result = reserve(db, payload)
        except SoldOut as error:
            self.json(409, {"error": str(error)})
        except (ValueError, OverflowError) as error:
            self.json(400, {"error": str(error)})
        else:
            self.json(201, result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get("COOKIE_DATABASE"), required="COOKIE_DATABASE" not in os.environ)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=9000)
    set_limit = commands.add_parser("set-limit")
    set_limit.add_argument("pickup")
    set_limit.add_argument("flavor", choices=FLAVORS)
    set_limit.add_argument("capacity", type=int)
    orders = commands.add_parser("orders")
    orders.add_argument("pickup")
    cancel = commands.add_parser("cancel")
    cancel.add_argument("id")
    args = parser.parse_args()
    with closing(connect(args.db)) as db, db:
        db.executescript(SCHEMA)
        if args.command == "set-limit":
            pickup_day(args.pickup)
            if args.capacity < 0:
                parser.error("Capacity must be at least zero.")
            db.execute("INSERT OR REPLACE INTO limits VALUES (?, ?, ?)", (args.pickup, args.flavor, args.capacity))
        elif args.command == "orders":
            pickup_day(args.pickup)
            for row in db.execute("SELECT * FROM orders WHERE pickup = ? ORDER BY name", (args.pickup,)):
                record = dict(row)
                record["quantities"] = dict(db.execute(
                    "SELECT flavor, quantity FROM quantities WHERE order_id = ? AND quantity > 0", (row["id"],)
                ))
                print(json.dumps(record))
        elif args.command == "cancel":
            if not db.execute("DELETE FROM orders WHERE id = ?", (args.id,)).rowcount:
                parser.error("Order not found.")
    if args.command == "serve":
        server = ThreadingHTTPServer((args.host, args.port), Handler)
        server.database = args.db
        server.serve_forever()


if __name__ == "__main__":
    main()

