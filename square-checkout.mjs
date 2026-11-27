const prices = {
  valedictorian: "Valedictorian",
  "all-nighter": "The All-Nighter",
  "party-animal": "Party Animal",
  overachiever: "Overachiever",
  "nutty-professor": "Nutty Professor",
};
const storefrontOrigin = "https://sarahtroup.github.io";
const checkoutHosts = new Set(["square.link", "sandbox.square.link", "checkout.square.site"]);
const eastern = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

function pickupTime(pickup, now = new Date()) {
  if (typeof pickup !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(pickup) || pickup < "2027-01-08") return null;
  const day = new Date(pickup + "T00:00:00Z");
  if (day.getUTCDay() !== 5 || day.toISOString().slice(0, 10) !== pickup) return null;
  const cutoffDay = new Date(day.getTime() - 7 * 86400000).toISOString().slice(0, 10);
  const {year, month, day: date, hour, minute} = Object.fromEntries(
    eastern.formatToParts(now).map(({type, value}) => [type, value])
  );
  if (`${year}-${month}-${date}T${hour}:${minute}` >= cutoffDay + "T09:30") return null;
  // 13:30 UTC is 9:30 a.m. in daylight time and 8:30 a.m. in standard time.
  const daylightCandidate = new Date(pickup + "T13:30:00Z");
  const localHour = eastern.formatToParts(daylightCandidate).find(part => part.type === "hour").value;
  return localHour === "09" ? daylightCandidate.toISOString() : pickup + "T14:30:00Z";
}

function respond(status, data) {
  return new Response(data === null ? null : JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": storefrontOrigin,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}

export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname !== "/checkout") return respond(404, {error: "Not found."});
    if (request.headers.get("Origin") !== storefrontOrigin) return respond(403, {error: "Open checkout from Campus Cookies."});
    if (request.method === "OPTIONS") return respond(204, null);
    if (request.method !== "POST") return respond(405, {error: "Use POST."});
    if (!request.headers.get("Content-Type")?.toLowerCase().startsWith("application/json")) {
      return respond(415, {error: "Send the order as JSON."});
    }
    let order;
    try {
      const raw = await request.text();
      if (raw.length > 4096) return respond(413, {error: "Order is too large."});
      order = JSON.parse(raw);
    } catch {
      return respond(400, {error: "Review your box and try again."});
    }

    const {id, pickup, quantities, gift, name, email} = order ?? {};
    const boxes = order?.boxes ?? [{quantities, gift}];
    const pickupAt = pickupTime(pickup);
    if (!pickupAt) return respond(400, {error: "Choose an available Friday. Orders close at 9:30 a.m. Eastern the Friday before pickup."});
    if (typeof id !== "string" || !/^[a-f0-9]{32}$/.test(id) ||
        typeof name !== "string" || !name.trim() || name.length > 100 ||
        typeof email !== "string" || email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ||
        !Array.isArray(boxes) || boxes.length < 1 || boxes.length > 10 ||
        !boxes.every(box => box && typeof box.gift === "boolean" && box.quantities &&
          Object.keys(box.quantities).length === 5 &&
          Object.keys(prices).every(key => Number.isInteger(box.quantities[key]) && box.quantities[key] >= 0 && box.quantities[key] <= 48) &&
          [6, 12, 24, 36, 48].includes(Object.values(box.quantities).reduce((total, qty) => total + qty, 0)))) {
      return respond(400, {error: "Review your contact information and fill the selected box size."});
    }

    if (!env.SQUARE_ACCESS_TOKEN || !env.SQUARE_LOCATION_ID) {
      return respond(503, {error: "Online payment is temporarily unavailable."});
    }
    const base = env.SQUARE_ENV === "production" ? "https://connect.squareup.com" : "https://connect.squareupsandbox.com";
    const items = boxes.flatMap(({quantities, gift}, index) => {
      const size = Object.values(quantities).reduce((total, qty) => total + qty, 0);
      const modifiers = Object.entries(prices).filter(([key]) => quantities[key] > 0).map(([key, label]) => ({
        name: `${quantities[key]} × ${label}`,
        base_price_money: {amount: 0, currency: "USD"},
      }));
      const boxLabel = boxes.length > 1 ? `Box ${index + 1}` : "Box";
      const boxItem = {
        name: `${boxLabel} – ${size} cookies`, quantity: "1", modifiers,
        base_price_money: {amount: size * 350, currency: "USD"},
      };
      if (!gift) return [boxItem];
      return [boxItem, {
        name: boxes.length > 1 ? `Gift box (Box ${index + 1})` : "Gift box",
        quantity: "1", base_price_money: {amount: 500, currency: "USD"},
      }];
    });
    const note = `Friday ${pickup}, 9:30 a.m.–3 p.m. ET, 1050 N. Davis Street, Jacksonville`;
    try {
      const response = await fetch(base + "/v2/online-checkout/payment-links", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.SQUARE_ACCESS_TOKEN}`,
          "Square-Version": "2026-11-18",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          idempotency_key: id,
          order: {
            location_id: env.SQUARE_LOCATION_ID, reference_id: id, line_items: items,
            fulfillments: [{
              type: "PICKUP", state: "PROPOSED",
              pickup_details: {
                schedule_type: "SCHEDULED", pickup_at: pickupAt, note,
                recipient: {display_name: name.trim(), email_address: email},
              },
            }],
          },
          payment_note: note,
        }),
        signal: AbortSignal.timeout(8000),
      });
      if (response.ok) {
        const link = new URL((await response.json()).payment_link.url);
        if (link.protocol === "https:" && checkoutHosts.has(link.hostname)) {
          return respond(200, {checkoutUrl: link.href});
        }
      }
    } catch {
      // Keep provider response details and credentials out of the storefront.
    }
    return respond(503, {error: "Square checkout is temporarily unavailable. Please try again."});
  },
};
