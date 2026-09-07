"""
OpenAPI tag descriptions (Step 10, Batch 10.11, requirement #14).

Purely presentational -- this is what turns the auto-generated docs at
/docs (Swagger UI) and /redoc (ReDoc) from an alphabetical dump of every
route into a grouped, described reference. One entry per router tag
(see app/api/router.py for the full list of routers/tags this must stay
in sync with); FastAPI matches these to route tags by name, so a typo
here just means that tag's description silently doesn't show -- it
never breaks anything at runtime.

Kept in its own module (rather than inline in main.py) so this list can
grow long without cluttering the app-construction code around it.
"""

TAGS_METADATA = [
    {
        "name": "health",
        "description": "Liveness/readiness check -- confirms the API is up and can reach the database. No authentication required.",
    },
    {
        "name": "auth",
        "description": "Signup, login, and token issuance. Every other endpoint (except `health`) requires the bearer token this returns.",
    },
    {
        "name": "businesses",
        "description": "Create, list, and manage a user's businesses. A user may own multiple businesses; every other business-scoped router below is nested under `/businesses/{business_id}/...` and authorizes against this business.",
    },
    {
        "name": "branches",
        "description": "Branches belonging to a business -- a business may have multiple physical/operational locations.",
    },
    {
        "name": "team",
        "description": "Team members and role-based permissions for a business (owner/admin/manager/staff). Invite, list, change role, remove.",
    },
    {
        "name": "billing",
        "description": "Subscription plans and usage limits at the business level, plus the Stripe checkout/webhook integration.",
    },
    {
        "name": "audit-logs",
        "description": "Read-only audit trail of business and account actions -- who did what, and when.",
    },
    {
        "name": "imports",
        "description": "Upload a transactions spreadsheet (.csv/.xlsx), map its columns, and confirm the import. Confirmation runs as a background job -- see the `queued` -> `completed`/`failed` status returned by `POST .../confirm` and pollable via `GET /imports/{id}`.",
    },
    {
        "name": "transactions",
        "description": "The core sales/transaction records a business's analytics, simulations, and alerts are all computed from.",
    },
    {
        "name": "analytics",
        "description": "Revenue/cost/profit summaries, time series, and breakdowns -- all computed via SQL aggregation over a business's own transactions.",
    },
    {
        "name": "chat",
        "description": "Conversation history for the AI assistant.",
    },
    {
        "name": "assistant",
        "description": "The AI business-assistant chat endpoint itself -- answers questions grounded in a business's own data.",
    },
    {
        "name": "simulations",
        "description": "The business-decision simulator -- run a live 'what if' scenario (price/volume change, etc.) or save one for later.",
    },
    {
        "name": "alerts",
        "description": "Automatically detected notable changes in a business's numbers (e.g. a revenue drop) -- both on-demand and via a scheduled background check.",
    },
    {
        "name": "google-integration",
        "description": "Connect a Google Sheet as a recurring transaction data source, synced on a schedule.",
    },
]
