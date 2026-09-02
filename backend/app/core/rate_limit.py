"""
Rate limiting (Step 10, Batch 10.5, requirement #7).

Uses slowapi (a thin FastAPI wrapper around the `limits` library) keyed
by client IP address. Storage is in-memory by default -- correct for
this app's current single-process Render deployment. If this ever scales
to multiple worker processes or instances behind a load balancer, each
process would enforce its own separate counters; switch to a shared
backend (Redis) via Limiter(storage_uri="redis://...") at that point so
limits are enforced consistently across all of them.

default_limits applies to every route unless overridden; auth routes get
a much stricter limit applied directly via @limiter.limit(...) since
brute-forcing login/signup is the highest-value target for rate limiting
specifically (requirement #7's "secure API authentication").
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
