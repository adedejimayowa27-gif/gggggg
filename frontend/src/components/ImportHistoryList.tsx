"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiFetch } from "@/lib/api";
import type { ImportSessionSummary } from "@/types";
import styles from "./ImportHistoryList.module.css";

interface Props {
  businessId: string;
  refreshSignal?: number;
}

function badgeClass(status: string): string {
  if (status === "completed") return styles.badgeCompleted;
  if (status === "failed") return styles.badgeFailed;
  return styles.badgePending;
}

export default function ImportHistoryList({ businessId, refreshSignal }: Props) {
  const { token } = useAuth();
  const [sessions, setSessions] = useState<ImportSessionSummary[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    apiFetch<ImportSessionSummary[]>(`/businesses/${businessId}/imports`, { authToken: token })
      .then(setSessions)
      .catch(() => setSessions(null))
      .finally(() => setIsLoading(false));
  }, [businessId, token, refreshSignal]);

  if (isLoading && !sessions) {
    return <p style={{ color: "var(--muted)" }}>Loading import history…</p>;
  }

  if (!sessions || sessions.length === 0) {
    return <div className={styles.empty}>No imports yet.</div>;
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.list}>
        {sessions.map((session) => (
          <div key={session.id} className={styles.row}>
            <div className={styles.rowLeft}>
              <span className={styles.filename}>{session.filename}</span>
              <span className={styles.date}>
                {new Date(session.created_at).toLocaleString()}
              </span>
            </div>
            <div className={styles.rowRight}>
              <span className={styles.counts}>
                {session.imported_row_count ?? "—"} imported ·{" "}
                {session.failed_row_count ?? "—"} failed of {session.total_row_count} total
              </span>
              <span className={`${styles.badge} ${badgeClass(session.status)}`}>
                {session.status.replace("_", " ")}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
