/**
 * Business settings (Step 13, Batch 3) -- mirrors PATCH /businesses/{id}
 * in backend/app/api/routes/business.py.
 */
import { apiFetch } from "@/lib/api";
import type { Business } from "@/types";

export interface BusinessSettingsInput {
  name?: string;
  industry?: string | null;
  auto_deduct_stock_on_sale?: boolean;
}

export function updateBusiness(businessId: string, input: BusinessSettingsInput, token: string): Promise<Business> {
  return apiFetch<Business>(`/businesses/${businessId}`, {
    method: "PATCH",
    authToken: token,
    body: JSON.stringify(input),
  });
}
