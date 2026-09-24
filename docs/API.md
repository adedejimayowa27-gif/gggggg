# API Documentation

Step 10, Batch 10.11, requirement #14. This is the developer guide for
the API's conventions -- the things that are true across *every*
endpoint, which the auto-generated schema reference doesn't state on
its own.

For the full endpoint-by-endpoint reference (every path, request/response
schema, and field), don't read this file for that -- use the
auto-generated, always-in-sync interactive docs the API serves itself:

- **Swagger UI:** `http://localhost:8000/docs` (try-it-out console)
- **ReDoc:** `http://localhost:8000/redoc` (cleaner read-only reference)
- **Raw OpenAPI schema:** `http://localhost:8000/openapi.json`

Endpoints are grouped there by the tags described in
`app/core/tags_metadata.py`.

## Authentication

Two tokens, both returned together (Step 12, Batch 12.3):

1. `POST /auth/signup` or `POST /auth/login` → returns
   `{ "access_token": "...", "refresh_token": "...", "user": {...} }`.
2. Send `access_token` back on every subsequent request:
   `Authorization: Bearer <access_token>`. It's a short-lived, stateless
   JWT (`ACCESS_TOKEN_EXPIRE_MINUTES` in `.env.example`, 15 min by
   default) -- no database lookup needed to verify it.
3. Before it expires, exchange it for a new pair with
   `POST /auth/refresh { "refresh_token": "..." }`. This rotates the
   refresh token -- the old one is revoked and the response contains a
   new one -- so store whichever refresh token you last received, never
   reuse an old one. (The frontend's `AuthContext` does this automatically
   shortly before each access token expires; see its module comment.)
4. `POST /auth/logout { "refresh_token": "..." }` revokes that session
   for real. The body is optional for backward compatibility, but without
   it nothing is revoked server-side.

Unlike `access_token`, `refresh_token` is opaque and stateful (checked
against `app.models.refresh_token.RefreshToken`, hashed at rest), which
is what makes revocation possible: on logout, and on
`POST /auth/reset-password` (which revokes every refresh token for that
account, so a compromised session can't outlive the password that was
reset because of it). Reusing an already-rotated refresh token is treated
as theft and revokes its entire session, not just that one token -- see
`app/models/refresh_token.py` and the `/auth/refresh` route's docstring
for the full mechanism.

### Two-factor login (Batch 12.6)

TOTP-based, using any standard authenticator app (Google Authenticator,
1Password, Authy, etc.):

- `POST /auth/2fa/setup` (authenticated) generates a new secret, returns
  it as `{ secret, otpauth_url, qr_code_svg }`. This does NOT enable
  2FA yet -- it's a pending enrollment until confirmed below. Calling
  it again before confirming replaces the pending secret; it can't be
  called at all while 2FA is already enabled (`409` -- disable first).
- `POST /auth/2fa/enable { "code": "123456" }` (authenticated) confirms
  the code matches the pending secret from setup, flips
  `is_2fa_enabled` to true, and returns `{ recovery_codes: [...] }` --
  8 one-time codes, shown exactly once, never retrievable again.
- With 2FA enabled, `POST /auth/login` no longer returns tokens
  directly: after the password checks out, it returns
  `{ two_factor_required: true, challenge_token }` instead. Redeem that
  at `POST /auth/2fa/verify-login { "challenge_token", "code" }`, which
  accepts either a live TOTP code or one of the recovery codes (a
  recovery code is consumed -- removed from the account -- on use), and
  returns a normal token response. The challenge token alone grants no
  access; it only proves the password was correct a few minutes ago
  (`TWO_FACTOR_CHALLENGE_EXPIRE_MINUTES`, default 10).
- `POST /auth/2fa/disable { "password", "code" }` and
  `POST /auth/2fa/recovery-codes { "password", "code" }` (regenerates
  the recovery-code set) both require the current password AND a
  current code (TOTP or recovery) -- proof of both factors, not just an
  active session, before touching 2FA settings.
- `GET /auth/me` and the data export now include `is_2fa_enabled`; the
  encrypted secret and recovery-code hashes are never exposed by any
  endpoint.

Requires `TOTP_ENCRYPTION_KEY` set on the server (same Fernet-key
pattern as `GOOGLE_TOKEN_ENCRYPTION_KEY`); `/2fa/setup` returns `503`
if it isn't.

### Exporting and deleting your own data (Batch 12.5)

- `GET /auth/me/export` downloads a JSON file with everything about the
  account: profile, businesses you own (with team-member and
  subscription summaries, but not raw transactions -- each business's
  existing `/businesses/{id}/transactions/export` is linked instead),
  team memberships on businesses you don't own, and your recent account
  activity from the audit log. Never includes the password hash, refresh
  tokens, or any integration's stored OAuth tokens.
- `DELETE /auth/me { "password": "..." }` permanently deletes the
  account and everything under it (owned businesses and all their data,
  team memberships, sessions). Requires the current password even
  though the request is already authenticated. Returns `409` if you own
  a business that still has other *active* team members -- remove them
  via `DELETE /businesses/{id}/team/{member_id}` first, since there's no
  way yet to delete just a business or transfer its ownership.

## The business/branch model (read this before calling anything else)

Every endpoint except `/health` and `/auth/*` is nested under
`/businesses/{business_id}/...`. A user can own multiple businesses
(`GET /businesses` lists them), and a business can have multiple team
members and multiple branches.

**Every one of those nested endpoints authorizes `business_id` against
the calling user on every single request** -- there is no cached
"current business" on the server side, and passing a `business_id` you
aren't authorized for returns `404 Not Found` (deliberately not `403`,
so an unauthorized caller can't even confirm the business exists). See
`app/api/deps.py`'s `get_owned_business`/`require_business_role` for the
implementation every route depends on.

## Roles and permissions

Every team member has one role on a business. Each role includes everything
the roles below it can do. A request from someone without a high enough role
gets the same `404 Business not found.` as a non-member (see above), so the
response never reveals what exists.

| Role | Can do |
|---|---|
| **Viewer** | Read everything the business shows: dashboard, analytics, transactions (including CSV export), alerts, import history, saved simulations, branches, the team list, subscription and integration status. Also use tools that change nothing: the what-if preview (`POST /simulate`), the AI assistant and chat history. |
| **Member** | Everyday work: upload and confirm imports, add and correct transactions and expenses by hand (`POST` / `PATCH .../transactions`, `.../expenses`), run Google Sheets / Excel syncs, run alert detection and mark alerts read/resolved/dismissed, save and delete simulations, add and edit branches. |
| **Admin** | Set up and manage: connect, configure and disconnect Google Sheets and Excel/OneDrive (including choosing the file and mapping columns), invite / change / remove team members, delete branches, delete transactions and expenses (`DELETE .../transactions/{id}`, `.../expenses/{id}`), read the audit log, start a plan upgrade (`POST .../billing/checkout`). |
| **Owner** | Everything an admin can. The business's creator; the owner role can't be assigned, changed or removed. Nothing is owner-only yet. |

Why integration setup is admin-only: listing spreadsheets or workbooks
shows the file names in the connected Google/Microsoft account, and choosing
the file and column mapping decides what data flows into the business.

### Adding, editing and deleting transactions

`POST /businesses/{id}/transactions` records one sale by hand (same fields an
import maps: date, product, quantity, selling price; optional cost price,
category, customer, payment method, branch). `PATCH .../transactions/{id}`
changes only the fields sent; the optional ones can be cleared with `null`.
`DELETE .../transactions/{id}` removes one. All three are audit-logged
(`transaction.created`, `transaction.updated`, `transaction.deleted`), and
creating counts toward the plan's monthly transaction limit.

Editing or deleting a row that came from a file import or a Sheets / Excel
sync remembers its original fingerprint (`transaction_tombstones`), so the
next sync or re-upload does not put the original row back or insert it as a
duplicate beside the corrected one. Deleting a manually entered sale leaves
no such record.

### Operating expenses and net profit

Operating expenses are the running costs that are **not** the cost of the
goods sold (rent, salaries, transport, electricity, airtime ...). The cost
of goods stays on each transaction (`cost_price`) and still produces
*gross profit*; expenses come off that to give *net profit*.

| Route | Who | What |
|---|---|---|
| `GET /businesses/{id}/expenses` | any role | Paginated list, newest first. Filters: `start_date`, `end_date`, `category` (case-insensitive), `q` (searches category and note), `branch_id`. Also returns `total_amount` for the whole filtered set. |
| `GET .../expenses/summary` | any role | Total, count and a per-category breakdown (largest first, with `share_percent`) for the same filters. |
| `GET .../expenses/categories` | any role | Categories already used, then suggested ones not yet used. |
| `POST .../expenses` | member | Add one. `date`, `category` and `amount` (> 0) are required; `description` and `branch_id` optional. |
| `PATCH .../expenses/{id}` | member | Change only the fields sent; `description` and `branch_id` can be cleared with `null`. |
| `DELETE .../expenses/{id}` | admin | Remove one. |

Writes are audit-logged (`expense.created`, `expense.updated`,
`expense.deleted`). Categories are free text; the breakdown groups them
case-insensitively, so "rent" and "Rent" are one line.

`GET .../analytics/summary` now also returns `operating_expenses`,
`expense_count`, `net_profit` and `net_profit_margin` for the same window.
`gross_profit` is unchanged. With no expenses recorded, `net_profit` equals
`gross_profit` and `expense_count` is `0`, which clients should surface
("no expenses recorded yet") rather than present as a final figure. In a
single-branch view (`branch_id`), only that branch's expenses count;
expenses with no branch are shared overhead and appear only in the
whole-business figures.

The AI assistant gains a `get_operating_expenses` tool, and `get_profit`
now returns `operating_expenses` and `net_profit`. The existing
`get_expenses` tool keeps its old meaning (cost of goods sold).

The OAuth redirects (`GET /google/callback`, `GET /microsoft/callback`) sit
outside `/businesses/{business_id}/...` because the providers send the
browser there without an Authorization header. They are authenticated by the
signed `state` value that only an admin's `/connect` call can generate.

**This table is enforced by a test.** `backend/tests/test_role_permissions.py`
holds the same table and fails if a business route has no declared role, if a
route enforces a different role than the table says, or if a
POST/PUT/PATCH/DELETE route is reachable by a Viewer without being
deliberately allow-listed. Adding an endpoint means adding its row there.

## Error responses

Every error response (validation, not-found, rate-limited, unexpected
server error -- all of them) has the same JSON shape:

```json
{
  "error": {
    "code": "not_found",
    "message": "Business not found.",
    "request_id": "3fae9b1c2e7a4d9d8e2f6a1b0c9d8e7f"
  }
}
```

`request_id` is also returned as the `X-Request-ID` response header on
*every* response (success or failure) -- hand this back when reporting
a problem; it's what ties a failed request to the exact structured log
line (and Sentry event, if error monitoring is configured -- see
`app/core/monitoring.py`) on the server side.

Common `code` values: `validation_error` (422, malformed request body),
`not_found` (404), `unauthorized` (401, missing/invalid/expired token),
`conflict` (409, e.g. duplicate email on signup), and endpoint-specific
codes for expected business-rule failures (e.g. `file_too_large`,
`too_many_rows`, `already_processed` -- see the relevant route's
docstring in `app/api/routes/` for the exhaustive list on that endpoint).

## Rate limits

Keyed by client IP. Exceeding a limit returns `429 Too Many Requests`.

| Route | Limit |
|---|---|
| `POST /auth/signup` | 5/minute |
| `POST /auth/login` | 10/minute |
| `POST /auth/refresh` | 30/minute |
| `POST /auth/forgot-password` | 5/minute |
| `POST /auth/reset-password` | 10/minute |
| `POST /auth/resend-verification` | 5/minute |
| `POST /auth/verify-email` | 10/minute |
| `GET /auth/me/export` | 5/minute |
| `DELETE /auth/me` | 3/minute |
| `POST /auth/2fa/verify-login` | 5/minute |
| `POST /auth/2fa/setup`, `/enable`, `/disable`, `/recovery-codes` | 10/minute |
| Everything else | 120/minute (default) |

(See `app/core/rate_limit.py`.)

## Background/async endpoints

Two endpoints don't return their final result synchronously -- they
return immediately with a status you poll:

- `POST /businesses/{id}/imports/{import_id}/confirm` → `202 Accepted`,
  `status: "queued"`. Poll `GET /businesses/{id}/imports/{import_id}`
  until `status` is `"completed"` or `"failed"`.

Everything else is synchronous: the response you get back is the final
result.

## Pagination

List endpoints (`GET /businesses/{id}/transactions`, `.../imports`,
`.../simulations`, `.../audit-logs`, etc.) use a simple `limit` query
parameter (each endpoint documents its own default and max in the
interactive docs) rather than cursor/offset pagination -- appropriate
for this app's current data volumes per business. Revisit if any
business's list of a given resource grows large enough that a flat
`limit` stops being sufficient.

## Multi-tenant security

This is covered in depth in the project's audit notes, but the short
version: a business must never be able to access another business's
data, and that's enforced at every layer (database FKs, backend query
scoping, the `get_owned_business`/`require_business_role` dependency
chain, and mirrored -- never solely relied upon -- in the frontend). If
you're adding a new endpoint: a route that only reads data depends on
`get_owned_business` (any active team member, including Viewers); a route
that creates, changes, deletes or triggers anything depends on
`require_business_role("member")` or higher (see "Roles and permissions"
above). Every query inside it must filter by that business's id. There is
no exception to this.
