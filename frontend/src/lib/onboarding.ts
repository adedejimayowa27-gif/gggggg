/**
 * Onboarding API helpers (Step 13, Batch 4) -- mirrors
 * backend/app/api/routes/onboarding.py and the import-template route.
 */
import { apiFetch, apiFetchBlob } from "@/lib/api";
import type { OnboardingStatus, SampleDataLoaded, SampleDataRemoved } from "@/types";

export function getOnboardingStatus(businessId: string, token: string): Promise<OnboardingStatus> {
  return apiFetch<OnboardingStatus>(`/businesses/${businessId}/onboarding`, { authToken: token });
}

export function loadSampleData(businessId: string, token: string): Promise<SampleDataLoaded> {
  return apiFetch<SampleDataLoaded>(`/businesses/${businessId}/sample-data`, {
    method: "POST",
    authToken: token,
  });
}

export function removeSampleData(businessId: string, token: string): Promise<SampleDataRemoved> {
  return apiFetch<SampleDataRemoved>(`/businesses/${businessId}/sample-data`, {
    method: "DELETE",
    authToken: token,
  });
}

/**
 * Downloads a blank CSV import template. The file is fetched with the
 * person's auth token (a plain link can't send it) and handed to the
 * browser as a synthetic download, same approach as the transaction
 * CSV export.
 */
export async function downloadImportTemplate(
  businessId: string,
  target: "transactions" | "expenses",
  token: string
): Promise<void> {
  const blob = await apiFetchBlob(`/businesses/${businessId}/imports/template?target=${target}`, {
    authToken: token,
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${target}-template.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
