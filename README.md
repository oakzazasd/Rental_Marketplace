# KMITL Rent — Student-to-Student Rental Marketplace

A full-stack rental marketplace where students of **King Mongkut's Institute of Technology
Ladkrabang (KMITL)** lend their own items to other students and borrow items from them.

One account is both a **borrower** and a **lender**. Borrowers pay a 5% service fee, lenders
pay a 10% platform fee, and lenders can advertise their listings through a category-competition
pricing model. Borrower ↔ lender communication happens in a **temporary chat room** that is
physically deleted from the database when the rental is completed, rejected or cancelled.

> This is a real working application: authentication, database persistence, pricing,
> rental workflow, advertising and chat are all implemented server-side. Nothing important is
> faked in the browser.

---

## Project Overview

| Area | What it does |
| --- | --- |
| Registration | KMITL-only (`@kmitl.ac.th`) registration validated on the backend, hashed passwords |
| Marketplace | Server-side search, category/price/availability filters, sorting, pagination |
| Item details | Multiple images, live server-side price quote, date picker, related items |
| Lending | Create / edit / delete listings, image upload, availability toggle, approve / reject |
| Borrowing | Request rentals, cancel, active rentals, history, total spent |
| Pricing | Daily price → long-term discount → 5% borrower fee / 10% lender fee, deposit kept separate |
| Availability | Backend overlap check: two rentals of the same item can never overlap in time |
| Advertising | Basic / Standard / Premium promotions priced from category competition |
| Search ranking | `final_score = relevance + promotion weight` (ads never bury relevant results) |
| Chat | One private room per rental request, polling, unread badges, permanent deletion |
| Dashboards | Borrower + lender summaries, earnings, transactions, promotion history |
| Banner ads | Responsive 728×90 / 320×100 placeholder component ready for a future ad server |

---

## Technology Stack

**Backend**

* Python 3.10+
* Flask 3 (application factory, blueprints)
* SQLAlchemy via Flask-SQLAlchemy (models, relationships, indexes, cascades)
* Flask-Login (session authentication) + Werkzeug password hashing
* Flask-WTF `CSRFProtect` (CSRF tokens on every POST, form or JSON)
* SQLite for development, `DATABASE_URL` ready for PostgreSQL
* Flask-Migrate (Alembic) for schema migrations
* Pillow for image validation, resizing and compression

**Frontend**

* Jinja2 templates, plain HTML/CSS/JavaScript
* Custom responsive orange design system (`app/static/css/style.css`)
* Lightweight polling for the chat (no WebSocket dependency)

---

## Project Structure

```text
project/
│
├── app/
│   ├── __init__.py          # application factory, blueprints, error handlers, upload route
│   ├── constants.py         # categories, statuses, labels, upload rules
│   ├── extensions.py        # db, login_manager, csrf
│   ├── models.py            # User, Item, RentalRequest, Transaction, ads, chat, configs
│   ├── seed_config.py       # idempotent default config rows (discounts, levels, fees)
│   ├── utils.py             # Decimal helpers, ฿ formatting, Jinja globals
│   │
│   ├── routes/
│   │   ├── auth.py          # /register /login /logout
│   │   ├── marketplace.py   # / , /items , /items/<id> , /api/items/<id>/quote
│   │   ├── dashboard.py     # /dashboard (borrower + lender overview)
│   │   ├── borrower.py      # /borrower/dashboard|requests|rentals|history
│   │   ├── lender.py        # /lender/dashboard|items|requests|rentals|earnings
│   │   ├── rentals.py       # request create, approve, reject, cancel, complete, detail
│   │   ├── advertising.py   # /lender/advertising/*
│   │   ├── chat.py          # /chat/<request_id> + JSON messages endpoints
│   │   └── profile.py       # /profile
│   │
│   ├── services/
│   │   ├── pricing.py       # calculate_rental_price() — all money maths (Decimal)
│   │   ├── rental.py        # availability, workflow, status sync, transaction totals
│   │   ├── advertising.py   # calculate_ad_price(), promotion weights, ad lifecycle
│   │   ├── chat.py          # room lifecycle, validation, sanitising, deletion
│   │   └── image.py         # secure upload: MIME/extension/size/resize/safe filenames
│   │
│   ├── templates/           # Jinja2 templates (+ components/, errors/)
│   ├── static/              # css/ js/
│   └── uploads/             # generated item images (git-ignored)
│
├── migrations/              # Alembic (Flask-Migrate) migrations
├── tests/                   # pytest suite (auth, items, rentals, pricing, ads, chat, search)
├── seed.py                  # demo data with fake .test accounts
├── config.py                # Config / TestConfig, env-driven settings
├── run.py                   # dev entry point
├── pytest.ini
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Installation

```bash
git clone <your-repo-url> rental_marketplace
cd rental_marketplace
```

### Virtual environment setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Environment variables

```bash
cp .env.example .env
```

| Variable | Purpose | Example |
| --- | --- | --- |
| `SECRET_KEY` | Session + CSRF secret (**never commit a real value**) | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///app.db` or `postgresql://user:pass@localhost:5432/rental` |
| `UPLOAD_FOLDER` | Where item images are stored | `app/uploads` |
| `MAX_CONTENT_LENGTH` | Max request/upload size in bytes (default 5 MB) | `5242880` |
| `SESSION_COOKIE_SECURE` | Set `1` when serving over HTTPS | `1` |
| `MAX_MESSAGE_LENGTH` | Max chat message length (default 2000) | `2000` |

No secret is hard-coded for production use: `SECRET_KEY` falls back to a development-only
value so the app still boots locally, but you **must** set it before deploying.

---

## Database Setup

Development creates the schema automatically on first start (`db.create_all()` plus the
default configuration rows: pricing config, discount tiers, promotion levels, competition
tiers, advertising base price).

```bash
python seed.py            # creates schema (if needed) + demo data
```

### Database migration

Schema changes are managed with Flask-Migrate (Alembic):

```bash
export FLASK_APP=run.py

# The factory auto-creates tables for development. Skip that while migrating:
SKIP_DB_INIT=1 flask db migrate -m "Describe your change"
SKIP_DB_INIT=1 flask db upgrade          # apply
flask db current                          # check the applied revision
```

* `migrations/versions/827b2740a827_initial_schema.py` — baseline schema.
* Switching to PostgreSQL later is only a `DATABASE_URL` change (all columns use portable
  types; money is `NUMERIC(12,2)` through the `Money` type decorator).

### Seed demo data

```bash
python seed.py            # add demo data (safe to re-run)
python seed.py --reset    # drop every table first
```

Demo accounts (password `password123`) use fake `.test` addresses so no mailbox is needed:

```text
student001@example.test    borrower + lender
student002@example.test    borrower
lender001@example.test     lender
lender002@example.test     lender
```

Demo items: Calculator, Camera, Tripod, Laptop, Projector, HDMI Cable, Textbook, Arduino Kit,
Drill Set, Badminton Rackets — with generated placeholder images, a pending request with an
open chat, an approved rental, a completed rental (chat already deleted) and two promotions.

Seeding inserts users directly through the ORM; **production registration still enforces
`@kmitl.ac.th`.**

---

## Running the Application

```bash
python run.py
# → http://127.0.0.1:5000
```

| Route | Page |
| --- | --- |
| `/` , `/items` | Marketplace (search, filters, sort) |
| `/items/<id>` | Item details + date picker + price quote |
| `/register` `/login` `/logout` | Authentication |
| `/dashboard` | Combined borrower + lender overview |
| `/borrower/dashboard` `/borrower/requests` `/borrower/rentals` `/borrower/history` | Borrower area |
| `/lender/dashboard` `/lender/items` `/lender/items/create` `/lender/items/<id>/edit` | Lender area |
| `/lender/requests` `/lender/rentals` `/lender/earnings` | Requests, rentals, money |
| `/lender/advertising` (+ `/promote`, `/quote`, `/<id>/cancel`) | Advertising |
| `/rentals/<id>` | Rental detail with the full price breakdown |
| `/chat/<rental_request_id>` | Temporary rental chat |
| `/profile` | Profile |

---

## Running Tests

```bash
pytest                    # full suite
pytest tests/test_pricing.py -v
pytest -k chat -v         # only chat tests
```

Coverage includes:

* **Auth** — valid KMITL registration, rejected domains, duplicates, password hashing,
  login/logout, protected routes, cross-user authorization.
* **Items** — create / edit / delete / availability toggle, image upload, invalid image,
  disallowed extension, generated filenames (no path traversal), image deletion.
* **Rentals** — request creation, invalid & past dates, overlap rejection, non-overlapping
  allowed, approve / reject / cancel permissions, completion, automatic status sync,
  third-user isolation, borrower vs lender price views.
* **Pricing** — 1/2/3/4/7/14/30 day cases verifying discount, 5% borrower fee, 10% lender
  fee, borrower total, lender payout, platform revenue, deposit separation and HALF_UP
  rounding.
* **Advertising** — competition tiers (1.0×/1.25×/1.5×/2.0×), Basic/Standard/Premium,
  durations, create/cancel, expired promotion weight = 0, sponsored labels, configurable
  levels.
* **Chat** — room created with the request, both participants allowed, third user denied
  (GET and POST), empty and oversized messages rejected, HTML sanitising, unread counts,
  permanent deletion after reject / cancel / complete, deleted rooms are unreachable.
* **Search** — relevance, promoted-laptop-below-relevant-calculator, promoted calculator
  first, expired promotion gives no boost, category/price/availability filters, sorting.

---

## Authentication Rules

* Only addresses ending in **`@kmitl.ac.th`** may register — checked in the WTForms
  validator (backend), not only in the browser.
* Email format, uniqueness (case-insensitive), student ID (8–12 digits, unique),
  password minimum length 8 and confirmation matching are all validated server-side.
* Passwords are stored as Werkzeug salted hashes — plaintext is never persisted.
* Sessions use `HttpOnly`, `SameSite=Lax` cookies (`SESSION_COOKIE_SECURE=1` for HTTPS),
  protected routes use `@login_required`, and every state change is CSRF-protected.
* Users can only see their own private pages (edit/delete/advertising/rentals/chat routes
  check ownership or participation and return 403/404 otherwise).

### Email verification architecture (future)

No fake "verification email sent" behaviour exists. The intended extension point is
documented in `app/routes/auth.py` (right after `login_user()` on registration): add an
`EmailVerification` token model, a `/verify/<token>` route, and gate the redirect there.
Nothing else in the authentication flow needs to change.

---

## Rental Pricing

All money maths lives in **`app/services/pricing.py`** — `calculate_rental_price()` returns
`base_amount, discount_rate, discount_amount, rental_subtotal, borrower_service_fee,
borrower_total, lender_platform_fee, lender_payout, platform_revenue, deposit,
amount_required`. Everything uses `Decimal` and rounds with `ROUND_HALF_UP` to 2 places.

```text
base_amount        = daily_price × rental_days
rental_subtotal    = base_amount − discount          (tier from RentalDiscount table)
borrower_service_fee = rental_subtotal × 5%
borrower_total     = rental_subtotal + borrower_service_fee
lender_platform_fee  = rental_subtotal × 10%
lender_payout      = rental_subtotal − lender_platform_fee
platform_revenue   = borrower_service_fee + lender_platform_fee
amount_required    = borrower_total + deposit        (deposit is never commissioned)
```

Discount tiers (stored in the `rental_discounts` table, editable without code changes):

```text
1 day       → 0%        2–3 days  → 3%       4–6 days → 5%
7–13 days   → 10%       14+ days  → 15%
```

Worked example — ฿100/day for 7 days with a ฿500 deposit:

```text
฿100 × 7                      = ฿700.00
Long-rental discount (10%)    = -฿70.00
Rental subtotal               = ฿630.00
Borrower service fee (5%)     = ฿31.50
Borrower total                = ฿661.50
Platform fee (10%)            = ฿63.00
Lender payout                 = ฿567.00
Platform revenue              = ฿94.50
Refundable deposit            = ฿500.00 (separate)
Amount required               = ฿1,161.50
```

Both sides see the full breakdown — no hidden fees. The numbers are snapshotted into the
`transactions` row when the request is created, then its `status` moves
`pending → authorized → completed` (or `refunded` on reject/cancel).

Rental length counts **both** the start and the end day (`(end − start).days + 1`), which is
also how overlapping date ranges are detected on the backend.

---

## Advertising Pricing

**`app/services/advertising.py` → `calculate_ad_price(category, promotion_level, duration_days)`**

```text
total_price = base_daily_price × competition_multiplier × promotion_level_multiplier × duration_days
```

* `base_daily_price` — `advertising_configs` table (default ฿20/day).
* **Category competition** — counted live from active listings in that category
  (`category_competition_configs`):

  ```text
  0–20 listings   → 1.0×      21–50 → 1.25×      51–100 → 1.5×      101+ → 2.0×
  ```

* **Promotion level** (`promotion_levels`, configurable):

  ```text
  Basic     → price 1.0×, ranking +10
  Standard  → price 1.5×, ranking +25
  Premium   → price 2.0×, ranking +50
  ```

* **Durations**: 1, 3, 7, 14, 30 days.

Example: Calculator category with 60 active listings → 1.5× competition; Premium →
฿20 × 1.5 × 2.0 = **฿60/day**; 7 days = **฿420**.

Purchase flow: choose item → choose level & duration → live AJAX price breakdown
(`POST /lender/advertising/quote`) → confirmation → `advertisements` row created with
`status = active`. **No real payment provider is integrated** (no Stripe/Opn/PromptPay) —
the code path for a payment step sits between the quote and `create_advertisement()`.

---

## Search Ranking

```text
final_score = relevance_score + promotion_weight (+ availability bonus)
```

* Relevance (capped at 100): name match +40, category +30, description +15, location +5 per
  query term.
* Promotion weight comes from an **active, in-window** advertisement (`0` for expired or
  cancelled promotions).
* A promoted listing always stays visible in the result set, but because relevance is capped
  high and promotion at +50, a *relevant* listing always outranks an unrelated promoted one:
  searching `calculator` ranks a promoted calculator first and puts a promoted laptop below
  the plain but relevant calculator.
* Every promoted card shows a **Sponsored** badge — paid listings are never disguised.
* Non-relevance sorts (`newest`, `price_asc`, `price_desc`) are exact; relevance sort applies
  the formula above.

---

## Temporary Chat System

* One `chat_rooms` row per `rental_requests` row, created together with the request.
* Only the **borrower** and the **item owner** may open the page or call the JSON endpoints —
  the backend checks participation on every request (changing `/chat/123` to `/chat/124`
  yields 403/404).
* Messages are plain text: HTML tags and control characters are stripped on write, Jinja
  auto-escapes on render, and the JS only ever inserts `textContent`.
* Validation: non-empty, max `MAX_MESSAGE_LENGTH` (default 2000).
* Unread indicator: per-room "last read" timestamps per participant → `Messages (n)` badge.
* New messages arrive by polling `GET /chat/<id>/messages?since=<last_id>` every 4 seconds.

**Deletion rules (real `DELETE`s, not hidden rows):**

| Transition | Effect |
| --- | --- |
| Request rejected | chat closed → messages deleted → room deleted |
| Request cancelled | chat closed → messages deleted → room deleted |
| Rental completed (or end date passed) | transaction finalised → messages deleted → room deleted |

After deletion neither party can retrieve the conversation. There is no global/inbox
messaging — chats exist only while a rental is being arranged.

---

## Image Upload Configuration

Handled by `app/services/image.py`:

* Allowed extensions: `jpg`, `jpeg`, `png`, `webp` **and** matching MIME types.
* Content sniffed with Pillow (`verify()` + `load()`), format must be JPEG/PNG/WEBP —
  a shell script named `evil.jpg` is rejected.
* Size limit: `MAX_CONTENT_LENGTH` (default 5 MB) plus a per-file check.
* Files are resized to max 1280 px and re-encoded (JPEG q85, or PNG when the image has
  transparency).
* Filenames are **generated** (`<uuid4>.<ext>`) — the original name is never used, so path
  traversal is impossible; the final path is verified to stay inside `UPLOAD_FOLDER`.
* Files live in `app/uploads/items/YYYYMM/…` and are served by a Flask route that uses
  `send_from_directory()` (traversal-safe).
* Items support multiple images; each image can be deleted from the edit page.

---

## UI / Design

* Orange primary actions/accents on white and light-grey surfaces, dark text, rounded cards,
  subtle shadows, modern navigation.
* Responsive at desktop / laptop / tablet / mobile: the navbar collapses, the marketplace grid
  and dashboards reflow, the chat is comfortable on phones, banners switch from 728×90 to
  320×100.
* Banner placeholders (`app/templates/components/_ad_banner.html`) are a macro that already
  accepts `image`, `url`, `alt`, `active`, `start_date`, `end_date` for a future ad server.
  Placement: marketplace (navbar → banner → filters → results), item details
  (information → banner → related items), dashboards (between sections).
* All amounts use Thai Baht formatting (`฿1,250.00`) everywhere.

---

## Error Handling

Custom friendly pages for `400`, `403`, `404` and `500`. The 500 handler rolls back the DB
session and never exposes a stack trace to the visitor (debug only in development).

---

## Security Checklist

* Salted password hashes (Werkzeug), no plaintext passwords ever stored or logged.
* Session + CSRF (`CSRFProtect`), `HttpOnly`/`SameSite` cookies, optional `Secure` flag.
* Backend validation for every form and every AJAX endpoint (KMITL domain, dates, prices,
  message length, promotion duration…).
* Authorization checks on every private route (ownership / participation), not just hidden UI.
* Output escaping by Jinja auto-escaping + plain-text chat storage.
* Upload validation (extension, MIME, magic bytes, size, generated names, path checks).
* Open-redirect protection on `?next=` after login.
* DB foreign keys with `ON DELETE CASCADE` (SQLite `PRAGMA foreign_keys=ON`), unique
  constraints and indexes on frequently filtered columns.
* Secrets come from the environment; `.env` is git-ignored.

---

## Production Deployment Notes

```bash
pip install gunicorn
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export DATABASE_URL="postgresql://user:password@host:5432/rental_marketplace"
export SESSION_COOKIE_SECURE=1
export UPLOAD_FOLDER=/var/www/rental_marketplace/uploads

flask --app run:app db upgrade     # apply migrations
gunicorn -w 4 -b 127.0.0.1:8000 run:app
```

* Use PostgreSQL in production (`DATABASE_URL`), keep SQLite for local development.
* Put a reverse proxy (nginx) in front and serve over HTTPS with `SESSION_COOKIE_SECURE=1`.
* Persist `UPLOAD_FOLDER` on a volume (or move to S3-compatible storage later).
* Set `FLASK_DEBUG=0` and a strong `SECRET_KEY`.
* Turn on automated backups and `flask db migrate` for every schema change.
* Future work that the architecture already accommodates: KMITL email verification, real
  payment processing for rentals/ads, real banner ads and ad analytics (impressions, clicks,
  CTR), notifications, reviews/ratings.

---

## License

Provided as a university project template — adapt as needed.
