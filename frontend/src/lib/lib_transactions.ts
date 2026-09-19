/**
 * Transaction field lookups -- mirrors GET
 * .../transactions/field-values in backend/app/api/routes/transactions.py.
 */
import { apiFetch } from "@/lib/api";

export type LookupField = "category" | "product" | "payment_method" | "customer";

export function fetchFieldValues(
  businessId: string,
  field: LookupField,
  token: string
): Promise<string[]> {
  return apiFetch<string[]>(`/businesses/${businessId}/transactions/field-values?field=${field}`, {
    authToken: token,
  });
}
