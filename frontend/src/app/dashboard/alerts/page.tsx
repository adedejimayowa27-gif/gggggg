"use client";

import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import AlertsPanel from "@/components/AlertsPanel";
import ComingSoon from "@/components/ComingSoon";

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
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>Alerts</h1>
      <AlertsPanel businessId={primaryBusiness.id} token={token} />
    </div>
  );
}
