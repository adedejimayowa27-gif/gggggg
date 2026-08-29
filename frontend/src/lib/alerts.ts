/**
 * Alert API helpers. Mirrors backend/app/api/routes/alerts.py.
 */
import { apiFetch } from "@/lib/api";
import type { Alert, AlertListItem, AlertStatus } from "@/types";

export function runAlertDetection(businessId: string, token: string): Promise<Alert[]> {
  return apiFetch<Alert[]>(`/businesses/${businessId}/alerts/run`, {
    method: "POST",
    authToken: token,
  });
}

export function listAlerts(
  businessId: string,
  token: string,
  status?: AlertStatus
): Promise<AlertListItem[]> {
  const qs = status ? `?status=${status}` : "";
  return apiFetch<AlertListItem[]>(`/businesses/${businessId}/alerts${qs}`, {
    authToken: token,
  });
}

export function getAlert(businessId: string, alertId: string, token: string): Promise<Alert> {
  return apiFetch<Alert>(`/businesses/${businessId}/alerts/${alertId}`, {
    authToken: token,
  });
}

export function updateAlertStatus(
  businessId: string,
  alertId: string,
  status: AlertStatus,
  token: string
): Promise<Alert> {
  return apiFetch<Alert>(`/businesses/${businessId}/alerts/${alertId}`, {
    method: "PATCH",
    authToken: token,
    body: JSON.stringify({ status }),
  });
}
