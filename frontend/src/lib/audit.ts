/**
 * Audit log API helper. Mirrors backend/app/api/routes/audit_logs.py.
 *
 * Requires "admin" role or higher on the business -- a plain member/
 * viewer gets a 404 (see require_business_role's not-403 reasoning in
 * app/api/deps.py), which the page using this should treat as "you
 * don't have access to this", not as a broken link.
 */
import { apiFetch } from "@/lib/api";
import type { AuditLogEntry } from "@/types";

export function listAuditLogs(
  businessId: string,
  token: string,
  limit: number = 100
): Promise<AuditLogEntry[]> {
  return apiFetch(`/businesses/${businessId}/audit-logs?limit=${limit}`, { authToken: token });
}
