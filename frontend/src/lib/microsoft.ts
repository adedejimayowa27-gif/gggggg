/**
 * Microsoft Excel/OneDrive integration API helpers. Mirrors
 * backend/app/api/routes/microsoft_integration.py, same shape as
 * lib/google.ts.
 */
import { apiFetch } from "@/lib/api";
import type {
  ExcelPreview,
  ExcelSyncResult,
  ExcelWorksheetItem,
  MicrosoftIntegrationStatus,
  WorkbookItem,
} from "@/types";

export function connectMicrosoft(businessId: string, token: string): Promise<{ authorization_url: string }> {
  return apiFetch(`/businesses/${businessId}/microsoft/connect`, { authToken: token });
}

export function getMicrosoftStatus(
  businessId: string,
  token: string
): Promise<MicrosoftIntegrationStatus | null> {
  return apiFetch(`/businesses/${businessId}/microsoft/status`, { authToken: token });
}

export function disconnectMicrosoft(businessId: string, token: string): Promise<void> {
  return apiFetch(`/businesses/${businessId}/microsoft`, { method: "DELETE", authToken: token });
}

export function listWorkbooks(businessId: string, token: string): Promise<WorkbookItem[]> {
  return apiFetch(`/businesses/${businessId}/microsoft/workbooks`, { authToken: token });
}

export function listExcelWorksheets(
  businessId: string,
  workbookItemId: string,
  token: string
): Promise<ExcelWorksheetItem[]> {
  return apiFetch(`/businesses/${businessId}/microsoft/workbooks/${workbookItemId}/worksheets`, {
    authToken: token,
  });
}

export function saveExcelSelection(
  businessId: string,
  workbookItemId: string,
  worksheetId: string,
  token: string
): Promise<MicrosoftIntegrationStatus> {
  return apiFetch(`/businesses/${businessId}/microsoft/selection`, {
    method: "PUT",
    authToken: token,
    body: JSON.stringify({ workbook_item_id: workbookItemId, worksheet_id: worksheetId }),
  });
}

export function previewExcelWorksheet(businessId: string, token: string): Promise<ExcelPreview> {
  return apiFetch(`/businesses/${businessId}/microsoft/preview`, { authToken: token });
}

export function saveExcelMapping(
  businessId: string,
  mapping: Record<string, string | null>,
  token: string
): Promise<MicrosoftIntegrationStatus> {
  return apiFetch(`/businesses/${businessId}/microsoft/mapping`, {
    method: "PUT",
    authToken: token,
    body: JSON.stringify({ mapping }),
  });
}

export function runExcelSync(businessId: string, token: string): Promise<ExcelSyncResult> {
  return apiFetch(`/businesses/${businessId}/microsoft/sync`, { method: "POST", authToken: token });
}
