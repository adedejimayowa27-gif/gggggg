"use client";

/**
 * Audit log page (frontend for Step 10, Batch 10.4's backend --
 * app/api/routes/audit_logs.py existed with no UI calling it until now).
 *
 * Requires "admin"+ role on the business (enforced by the backend via
 * require_business_role -- see app/api/deps.py); a plain member/viewer
 * gets a 404 from the API, shown here as an access notice rather than a
 * generic error, since it's an expected/correct outcome, not a bug.
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { ApiError } from "@/lib/api";
import { listAuditLogs } from "@/lib/audit";
import type { AuditLogEntry } from "@/types";
import ComingSoon from "@/components/ComingSoon";
import styles from "./audit-log.module.css";

function formatAction(action: string): string {
  return action.replace(/_/g, " ").replace(/\./g, " · ");
}

export default function AuditLogPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses, currentUserRole } = useDashboard();

  const [logs, setLogs] = useState<AuditLogEntry[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !primaryBusiness) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setAccessDenied(false);
    listAuditLogs(primaryBusiness.id, token)
      .then((result) => {
        if (!cancelled) setLogs(result);
      })
      .catch((err) => {
        if (cancelled) return;
        // The backend returns 404 (not 403) for a member/viewer without
        // admin access, matching how it treats any other unauthorized
        // business access -- see app/api/deps.py's reasoning.
        if (err instanceof ApiError && err.status === 404) {
          setAccessDenied(true);
        } else {
          setError(err instanceof ApiError ? err.message : "Could not load the audit log.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, primaryBusiness]);

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness || !token) {
    return <ComingSoon title="Audit Log" description="Create a business to see its audit trail here." />;
  }

  if (accessDenied) {
    return (
      <ComingSoon
        title="Audit Log"
        description={
          currentUserRole
            ? "Viewing the audit log requires admin access on this business."
            : "You don't have access to this business's audit log."
        }
      />
    );
  }

  return (
    <div>
      <div className={styles.header}>
        <h1>Audit Log</h1>
      </div>

      {error && <p className={styles.error}>{error}</p>}
      {isLoading ? (
        <p style={{ color: "var(--muted)" }}>Loading…</p>
      ) : (
        <div className={styles.list}>
          {logs?.map((entry) => (
            <div key={entry.id} className={styles.row}>
              <div className={styles.rowLeft}>
                <span className={styles.action}>{formatAction(entry.action)}</span>
                {entry.target_type && (
                  <span className={styles.target}>
                    {entry.target_type}
                    {entry.target_id ? ` · ${entry.target_id.slice(0, 8)}` : ""}
                  </span>
                )}
              </div>
              <span className={styles.timestamp}>{new Date(entry.created_at).toLocaleString()}</span>
            </div>
          ))}
          {logs?.length === 0 && <p style={{ color: "var(--muted)" }}>No activity recorded yet.</p>}
        </div>
      )}
    </div>
  );
}
