/**
 * Google Sheets integration API helpers. Mirrors
 * backend/app/api/routes/google_integration.py.
 */
import { apiFetch } from "@/lib/api";
import type {
  GoogleIntegrationStatus,
  SheetPreview,
  SpreadsheetItem,
  SyncResult,
  WorksheetItem,
} from "@/types";

export function connectGoogle(businessId: string, token: string): Promise<{ authorization_url: string }> {
  return apiFetch(`/businesses/${businessId}/google/connect`, { authToken: token });
}

export function getGoogleStatus(
  businessId: string,
  token: string
): Promise<GoogleIntegrationStatus | null> {
  return apiFetch(`/businesses/${businessId}/google/status`, { authToken: token });
}

export function disconnectGoogle(businessId: string, token: string): Promise<void> {
  return apiFetch(`/businesses/${businessId}/google`, { method: "DELETE", authToken: token });
}

export function listSpreadsheets(businessId: string, token: string): Promise<SpreadsheetItem[]> {
  return apiFetch(`/businesses/${businessId}/google/spreadsheets`, { authToken: token });
}

export function listWorksheets(
  businessId: string,
  spreadsheetId: string,
  token: string
): Promise<WorksheetItem[]> {
  return apiFetch(`/businesses/${businessId}/google/spreadsheets/${spreadsheetId}/worksheets`, {
    authToken: token,
  });
}

export function saveSelection(
  businessId: string,
  spreadsheetId: string,
  worksheetTitle: string,
  token: string
): Promise<GoogleIntegrationStatus> {
  return apiFetch(`/businesses/${businessId}/google/selection`, {
    method: "PUT",
    authToken: token,
    body: JSON.stringify({ spreadsheet_id: spreadsheetId, worksheet_title: worksheetTitle }),
  });
}

export function previewSheet(businessId: string, token: string): Promise<SheetPreview> {
  return apiFetch(`/businesses/${businessId}/google/preview`, { authToken: token });
}

export function saveMapping(
  businessId: string,
  mapping: Record<string, string | null>,
  token: string
): Promise<GoogleIntegrationStatus> {
  return apiFetch(`/businesses/${businessId}/google/mapping`, {
    method: "PUT",
    authToken: token,
    body: JSON.stringify({ mapping }),
  });
}

export function runSync(businessId: string, token: string): Promise<SyncResult> {
  return apiFetch(`/businesses/${businessId}/google/sync`, { method: "POST", authToken: token });
}
