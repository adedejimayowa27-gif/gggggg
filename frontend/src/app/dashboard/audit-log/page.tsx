"use client";

/**
 * Audit log page (frontend for Step 10, Batch 10.4's backend --
 * app/api/routes/audit_logs.py existed with no UI calling it until now).
 *
 * Requires "admin"+ role on the business (enforced by the backend via
 * require_business_role -- see app/api/deps.py); a plain member/viewer
 * gets a 404 from the API, shown here as an access notice rather than a
 * generic error, since it's an expected/correct outcome, not a bug.
 *
 * Reform pass -- both operational and visual:
 * - The log previously showed the action and target but never who did
 *   it -- actor_user_id was fetched but never displayed (and wasn't
 *   human-readable anyway, just a UUID). The backend now resolves it to
 *   a name/email (see routes/audit_logs.py), shown here with a colored
 *   initial avatar, matching the Team page's identity treatment.
 * - Timestamps were a verbose full locale string; now a relative time
 *   ("2h ago") with the exact timestamp available on hover via title,
 *   matching the pattern used on Alerts.
 * - Tokens instead of hardcoded hex, row hover-lift, icon chip header.
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { ApiError } from "@/lib/api";
import { listAuditLogs } from "@/lib/audit";
import type { AuditLogEntry } from "@/types";
import ComingSoon from "@/components/ComingSoon";
import styles from "./audit-log.module.css";

const AVATAR_ACCENTS = ["avatarGold", "avatarLeaf", "avatarPurple", "avatarBlue"] as const;

function avatarAccentFor(key: string): (typeof AVATAR_ACCENTS)[number] {
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  return AVATAR_ACCENTS[hash % AVATAR_ACCENTS.length];
}

function formatAction(action: string): string {
  return action.replace(/_/g, " ").replace(/\./g, " · ");
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  return new Date(iso).toLocaleDateString();
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
        <div className={styles.headerText}>
          <h1>Audit Log</h1>
          <p className={styles.subtitle}>Who did what on this business, most recent first.</p>
        </div>
      </div>

      {error && <p className={styles.error}>{error}</p>}
      {isLoading ? (
        <p style={{ color: "var(--muted)" }}>Loading…</p>
      ) : logs?.length === 0 ? (
        <div className={styles.emptyState}>No activity recorded yet.</div>
      ) : (
        <div className={styles.list}>
          {logs?.map((entry) => {
            const name = entry.actor_display_name;
            const initial = name ? name.trim().charAt(0).toUpperCase() : "?";
            const accent = avatarAccentFor(name ?? "system");
            return (
              <div key={entry.id} className={styles.row}>
                <div className={styles.rowLeft}>
                  <span className={`${styles.avatar} ${styles[accent]}`}>{initial}</span>
                  <div className={styles.rowText}>
                    <div className={styles.actionLine}>
                      <span className={styles.actor}>{name ?? "System"}</span>
                      <span className={styles.action}>{formatAction(entry.action)}</span>
                    </div>
                    {entry.target_type && (
                      <span className={styles.target}>
                        {entry.target_type}
                        {entry.target_id ? ` · ${entry.target_id.slice(0, 8)}` : ""}
                      </span>
                    )}
                  </div>
                </div>
                <span className={styles.timestamp} title={new Date(entry.created_at).toLocaleString()}>
                  {relativeTime(entry.created_at)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
