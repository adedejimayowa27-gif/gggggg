/**
 * Billing API helpers. Mirrors backend/app/api/routes/billing.py.
 *
 * The checkout endpoint returns a 503 (surfaced as an ApiError with
 * code "billing_not_configured") until a real STRIPE_SECRET_KEY is set
 * on the backend -- see app/services/billing.py's _require_stripe_configured.
 * The UI using this should handle that case rather than treat it as an
 * unexpected error.
 */
import { apiFetch } from "@/lib/api";
import type { Plan, Subscription } from "@/types";

export function listPlans(token: string): Promise<Plan[]> {
  return apiFetch(`/plans`, { authToken: token });
}

export function getSubscription(businessId: string, token: string): Promise<Subscription> {
  return apiFetch(`/businesses/${businessId}/subscription`, { authToken: token });
}

export function startCheckout(
  businessId: string,
  input: { plan_key: string; success_url: string; cancel_url: string },
  token: string
): Promise<{ checkout_url: string }> {
  return apiFetch(`/businesses/${businessId}/billing/checkout`, {
    method: "POST",
    authToken: token,
    body: JSON.stringify(input),
  });
}
