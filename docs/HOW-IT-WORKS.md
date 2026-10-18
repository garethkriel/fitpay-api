# How FitPay works

A walkthrough of the code in plain English, so you can explain any part of it in an interview.

## The layers

Each layer only talks to the one below it:

```
HTTP request
  -> api/routes/*.py     checks the input (Pydantic), picks the right service
  -> services.py         the business logic: create a client, apply a payment, build a report
  -> billing.py          pure rules: paid-up dates, client status, rand formatting
     payfast.py          pure rules: signatures, checkout fields, notification checks
  -> models.py / db.py   the database tables (SQLAlchemy)
```

`billing.py` and `payfast.py` don't touch the database or the web. That makes them the easiest
code to test, and the most important code to get right.

## Following one request

`POST /clients/3/payments` with `{"amount_cents": 100000, "months": 1, "method": "eft", "paid_on": "2026-10-01"}`:

1. **FastAPI** matches the URL to `add_payment` in `api/routes/clients.py`.
2. Before the function runs, FastAPI resolves its **dependencies** (`api/deps.py`):
   - `require_admin` checks the `X-API-Key` header, using `secrets.compare_digest` so the check
     takes the same time whether the key is nearly right or completely wrong.
   - `get_session` opens a database session and closes it after the response.
   - `get_settings` and `get_today` supply the settings and today's date.
3. **Pydantic** turns the JSON into a `ManualPaymentIn` object. If `amount_cents` were 0 or
   `paid_on` weren't a date, FastAPI would return a 422 error before the function runs.
4. `services.record_manual_payment` refuses `method: "payfast"` (only PayFast's own notification
   may record those), saves a `Payment` row with status `complete`, and reloads the client.
5. `services.detail` works out the client's status with `billing.client_status` and returns a
   `ClientDetail`, which FastAPI turns back into JSON.

## The billing rules (`billing.py`)

A client is covered from their **start date** for as many months as they've paid for:

> Start date 10 January. Two monthly payments: paid until 10 March.

Their status compares that date with today:

| Paid until vs today | Monthly plan | Once-off program |
| --- | --- | --- |
| Never paid | `not_paid` | `not_paid` |
| More than 7 days away | `up_to_date` | `up_to_date` |
| 0–7 days away | `due_soon` | `up_to_date` |
| In the past | `overdue` | `finished` |

`add_months` handles short months: 31 January plus one month is 28 February (29 in a leap year).
Counting from the start date rather than from payment dates means paying a few days early or late
never gains or loses cover.

## PayFast (`payfast.py`)

**Checkout.** `POST /checkout` creates a *pending* payment with a random reference (a UUID) and
returns the form fields to post to PayFast. PayFast checks a `signature` field:

1. Take the fields in order as `name=value`, joined with `&`. Leave out blank ones.
2. URL-encode the values: spaces become `+`, and `/` becomes `%2F`.
3. Add `&passphrase=...` if the merchant set one.
4. MD5 the whole string.

`test_signature_matches_payfast_rules_written_out_by_hand` builds that string by hand and checks
that the code produces the same hash.

**Notification (ITN).** After the client pays, PayFast POSTs to `/payfast/notify`. Anyone could
POST to that URL, so before trusting it the API checks:

- **The signature** is recalculated from the fields in the order they arrived. That's why the
  route reads the raw body with `parse_qsl` instead of letting FastAPI parse it: a dictionary could
  change the order.
- **The merchant ID** is ours.
- **The amount** matches the pending payment. Otherwise someone could pay R1 for a R1 000 package.

Only then is the payment marked `complete`.

**Idempotency.** PayFast retries a notification until it gets a 200 response, so the same message
can arrive twice. `apply_notification` returns early if the payment is already complete with the
same `pf_payment_id`, and refuses (409) if a *different* PayFast payment claims the same reference.

## Money

Amounts are stored as **integers in cents** (R1 200.00 is `120000`). Floats can't store most
decimal amounts exactly (`0.1 + 0.2` is `0.30000000000000004`), and that's not acceptable for money.
`format_rands` turns cents into `R1 200.00` for display.

## Tests

- `tests/conftest.py` builds a fresh app for every test with an **in-memory SQLite** database,
  so tests never share data and run in about a second.
- "Today" is fixed to 18 October 2026 by overriding the `get_today` dependency. Without that, a
  test that passes today could fail next month.
- `test_billing.py` and `test_payfast.py` test the pure functions directly. `test_api.py` goes
  through HTTP like a real client would.

Run `pytest --cov=fitpay` to see which lines the tests cover (currently about 96%).

## Interview questions you might get

**Why FastAPI?** It uses type hints to validate requests and generate the `/docs` page
automatically, and its dependency injection makes things like the database session and the admin
check easy to reuse and to swap out in tests.

**What does `Depends` do?** It tells FastAPI to call another function first and pass its result in.
`get_session` uses `yield`, so FastAPI also closes the session after the response.

**Why store money in cents?** Floating-point numbers can't represent most decimals exactly.
Integers can, so totals always add up.

**How do you stop someone faking a PayFast notification?** Check the signature with our
passphrase, check the merchant ID, and check that the amount matches what we expected. PayFast also
offers a server-to-server validation call and a list of its IP addresses; adding those is on the roadmap.

**What happens if PayFast sends the same notification twice?** The second one is accepted and does
nothing, because the payment is already complete with that PayFast ID.

**Why is "today" a dependency?** So tests can fix the date. Status depends on the date, and tests
must give the same result every day.

**What would you add next?** Alembic migrations, so the database can change without being
recreated; email reminders for clients who are due soon; and PayFast subscriptions for monthly plans.

## Ideas to practise on

Good small changes to make yourself, each with a test:

1. Add `DELETE /packages/{id}` that refuses if any client is on that package.
2. Add `GET /reports/due-soon`, like `/reports/overdue`.
3. Add a `fitpay export` command that writes `payments.csv` to a file.
4. Add a `total_paid` field to `ClientDetail`.
