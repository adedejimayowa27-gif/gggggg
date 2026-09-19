"use client";

import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import AlertsPanel from "@/components/AlertsPanel";
import ComingSoon from "@/components/ComingSoon";
import styles from "./alerts.module.css";

export default function AlertsPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness || !token) {
    return <ComingSoon title="Alerts" description="Create a business to start seeing alerts here." />;
  }

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h1>Alerts</h1>
          <p className={styles.subtitle}>Anomalies and risks worth a second look, ranked by severity.</p>
        </div>
      </div>
      <AlertsPanel businessId={primaryBusiness.id} token={token} />
    </div>
  );
}
