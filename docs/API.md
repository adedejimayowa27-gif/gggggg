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

Stateless JWT bearer tokens.

1. `POST /auth/signup` or `POST /auth/login` → returns `{ "access_token": "...", "user": {...} }`.
2. Send it back on every subsequent request: `Authorization: Bearer <access_token>`.
3. `POST /auth/logout` exists for a consistent API shape (and to leave
   room for future server-side revocation) but logout is currently a
   client-side action -- just discard the token.

There is no refresh-token flow yet: a token is valid until it expires
(see `ACCESS_TOKEN_EXPIRE_MINUTES` in `.env.example`), at which point the
client re-authenticates via `/auth/login`.

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
you're adding a new endpoint: it must depend on `get_owned_business` (or
`require_business_role` if it needs a minimum team role) and every query
inside it must filter by that business's id. There is no exception to
this.
