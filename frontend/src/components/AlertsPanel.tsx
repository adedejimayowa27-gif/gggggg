"use client";

/**
 * Displays a business's alerts, severity-coded, with mark read/dismiss/
 * resolve actions (requirement #6). `compact` shows only unread/read
 * alerts capped at a few items (for the Overview page, requirement #7 --
 * "prominently on the dashboard"); the full mode (used on
 * /dashboard/alerts) shows a status filter and the complete list.
 */
import { useEffect, useState } from "react";
import { listAlerts, runAlertDetection, updateAlertStatus } from "@/lib/alerts";
import type { AlertListItem, AlertStatus } from "@/types";
import styles from "./AlertsPanel.module.css";

const SEVERITY_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

interface Props {
  businessId: string;
  token: string;
  compact?: boolean;
}

export default function AlertsPanel({ businessId, token, compact = false }: Props) {
  const [alerts, setAlerts] = useState<AlertListItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<AlertStatus | "all">(compact ? "all" : "unread");
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    setError(null);
    listAlerts(businessId, token, statusFilter === "all" ? undefined : statusFilter)
      .then((items) => {
        const filtered = compact ? items.filter((a) => a.status === "unread" || a.status === "read") : items;
        setAlerts(
          [...filtered].sort(
            (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
          )
        );
      })
      .catch(() => setError("Could not load alerts."))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [businessId, token, statusFilter]);

  const handleRun = () => {
    setIsRunning(true);
    runAlertDetection(businessId, token)
      .then(load)
      .catch(() => setError("Could not run alert detection."))
      .finally(() => setIsRunning(false));
  };

  const handleStatusChange = (id: string, status: AlertStatus) => {
    updateAlertStatus(businessId, id, status, token).then(load);
  };

  const visible = compact ? alerts.slice(0, 5) : alerts;

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h2>{compact ? "Alerts" : "All Alerts"}</h2>
        <div className={styles.headerActions}>
          {!compact && (
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as AlertStatus | "all")}
              className={styles.statusSelect}
            >
              <option value="all">All</option>
              <option value="unread">Unread</option>
              <option value="read">Read</option>
              <option value="dismissed">Dismissed</option>
              <option value="resolved">Resolved</option>
            </select>
          )}
          <button className={styles.runButton} onClick={handleRun} disabled={isRunning}>
            {isRunning ? "Checking…" : "Check for alerts"}
          </button>
        </div>
      </div>

      {error && <p className={styles.error}>{error}</p>}
      {isLoading && <p className={styles.muted}>Loading…</p>}
      {!isLoading && visible.length === 0 && (
        <p className={styles.muted}>No alerts right now -- everything looks normal.</p>
      )}

      <ul className={styles.list}>
        {visible.map((alert) => (
          <li key={alert.id} className={styles.item}>
            <span className={`${styles.severityDot} ${styles[`severity_${alert.severity}`]}`} />
            <div className={styles.itemBody}>
              <div className={styles.itemTitleRow}>
                <strong>{alert.title}</strong>
                <span className={styles.severityLabel}>{alert.severity}</span>
              </div>
              <p className={styles.itemMessage}>{alert.message}</p>
              {(alert.affected_product || alert.affected_category || alert.affected_metric) && (
                <p className={styles.itemMeta}>
                  {[alert.affected_product, alert.affected_category, alert.affected_metric]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              )}
            </div>
            <div className={styles.itemActions}>
              {alert.status === "unread" && (
                <button onClick={() => handleStatusChange(alert.id, "read")}>Mark read</button>
              )}
              {alert.status !== "dismissed" && alert.status !== "resolved" && (
                <>
                  <button onClick={() => handleStatusChange(alert.id, "resolved")}>Resolve</button>
                  <button onClick={() => handleStatusChange(alert.id, "dismissed")}>Dismiss</button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
