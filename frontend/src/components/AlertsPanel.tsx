"use client";

/**
 * Displays a business's alerts, severity-coded, with mark read/dismiss/
 * resolve actions. `compact` shows only unread/read alerts capped at a
 * few items (for the Overview page -- "prominently on the dashboard");
 * the full mode (used on /dashboard/alerts) shows a status filter and
 * the complete list.
 *
 * Reform pass -- both visual and operational:
 * - Tokens instead of hardcoded hex, the same white-on-gold contrast
 *   bug fixed elsewhere fixed here too, severity dots upgraded to
 *   labeled badges, cards get the hover-lift treatment used everywhere
 *   else in the redesign.
 * - Status filter is now a tab control (matches the Category/Customer/
 *   Payment tabs elsewhere) instead of a native <select>, and an unread
 *   count badge sits next to the title so urgency is visible without
 *   opening the filter at all.
 * - "Check for alerts" now says what it found ("3 new alerts" / "no
 *   new issues") instead of silently reloading the list with no
 *   feedback on whether anything happened.
 * - Each alert shows a relative timestamp, so "how urgent is this
 *   really" doesn't require cross-referencing a date by hand.
 */
import { useEffect, useState } from "react";
import { useDashboard } from "@/context/DashboardContext";
import { listAlerts, runAlertDetection, updateAlertStatus } from "@/lib/alerts";
import { hasRole } from "@/lib/permissions";
import type { AlertListItem, AlertStatus } from "@/types";
import styles from "./AlertsPanel.module.css";

const SEVERITY_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

const STATUS_TABS: { key: AlertStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "read", label: "Read" },
  { key: "dismissed", label: "Dismissed" },
  { key: "resolved", label: "Resolved" },
];

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  const diffMonth = Math.floor(diffDay / 30);
  return `${diffMonth}mo ago`;
}

interface Props {
  businessId: string;
  token: string;
  compact?: boolean;
}

export default function AlertsPanel({ businessId, token, compact = false }: Props) {
  // Batch 12.4: checking for alerts and changing an alert's status need the
  // "member" role; a read-only viewer still sees every alert.
  const { currentUserRole } = useDashboard();
  const canManageAlerts = hasRole(currentUserRole, "member");

  const [alerts, setAlerts] = useState<AlertListItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<AlertStatus | "all">(compact ? "all" : "unread");
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runFeedback, setRunFeedback] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    setError(null);
    listAlerts(businessId, token, statusFilter === "all" ? undefined : statusFilter)
      .then((items) => {
        const filtered = compact ? items.filter((a) => a.status === "unread" || a.status === "read") : items;
        setAlerts([...filtered].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]));
      })
      .catch(() => setError("Could not load alerts."))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [businessId, token, statusFilter]);

  const handleRun = () => {
    setIsRunning(true);
    setRunFeedback(null);
    runAlertDetection(businessId, token)
      .then((newAlerts) => {
        setRunFeedback(
          newAlerts.length === 0
            ? "No new issues found."
            : `${newAlerts.length} new ${newAlerts.length === 1 ? "alert" : "alerts"} found.`
        );
        load();
      })
      .catch(() => setError("Could not run alert detection."))
      .finally(() => setIsRunning(false));
  };

  const handleStatusChange = (id: string, status: AlertStatus) => {
    updateAlertStatus(businessId, id, status, token).then(load);
  };

  const visible = compact ? alerts.slice(0, 5) : alerts;
  const unreadCount = alerts.filter((a) => a.status === "unread").length;

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.iconWrap}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path
                d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path d="M13.73 21a2 2 0 01-3.46 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </div>
          <div className={styles.headerTextGroup}>
            <h2 className={styles.title}>
              {compact ? "Alerts" : "All Alerts"}
              {!compact && unreadCount > 0 && <span className={styles.unreadBadge}>{unreadCount}</span>}
            </h2>
          </div>
        </div>
        {canManageAlerts && (
          <button className={styles.runButton} onClick={handleRun} disabled={isRunning}>
            {isRunning ? "Checking…" : "Check for alerts"}
          </button>
        )}
      </div>

      {!compact && (
        <div className={styles.tabs}>
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`${styles.tab} ${statusFilter === tab.key ? styles.tabActive : ""}`}
              onClick={() => setStatusFilter(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {runFeedback && <p className={styles.runFeedback}>{runFeedback}</p>}
      {error && <p className={styles.error}>{error}</p>}

      {isLoading ? (
        <p className={styles.muted}>Loading…</p>
      ) : visible.length === 0 ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path
                d="M20 6L9 17l-5-5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <p className={styles.emptyText}>No alerts right now -- everything looks normal.</p>
        </div>
      ) : (
        <ul className={styles.list}>
          {visible.map((alert) => (
            <li key={alert.id} className={styles.item}>
              <span
                className={`${styles.severityBadge} ${styles[`severity_${alert.severity}`]}`}
              >
                {alert.severity}
              </span>
              <div className={styles.itemBody}>
                <div className={styles.itemTitleRow}>
                  <strong>{alert.title}</strong>
                  <span className={styles.itemTime}>{relativeTime(alert.created_at)}</span>
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
              {canManageAlerts && (
                <div className={styles.itemActions}>
                  {alert.status === "unread" && (
                    <button className={styles.actionNeutral} onClick={() => handleStatusChange(alert.id, "read")}>
                      Mark read
                    </button>
                  )}
                  {alert.status !== "dismissed" && alert.status !== "resolved" && (
                    <>
                      <button
                        className={styles.actionPositive}
                        onClick={() => handleStatusChange(alert.id, "resolved")}
                      >
                        Resolve
                      </button>
                      <button
                        className={styles.actionNeutral}
                        onClick={() => handleStatusChange(alert.id, "dismissed")}
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
