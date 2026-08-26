"use client";

import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import type { DateRangeValue } from "@/types";
import DateRangePicker from "@/components/DateRangePicker";
import RevenueProfitChart from "@/components/RevenueProfitChart";
import ComingSoon from "@/components/ComingSoon";
import styles from "./analytics.module.css";

export default function AnalyticsPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();
  const [dateRange, setDateRange] = useState<DateRangeValue>({ range: "30d" });

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness || !token) {
    return (
      <ComingSoon
        title="Analytics"
        description="Create a business to start seeing revenue and profit trends here."
      />
    );
  }

  return (
    <div>
      <div className={styles.header}>
        <h1>Analytics</h1>
        <DateRangePicker value={dateRange} onChange={setDateRange} />
      </div>

      <RevenueProfitChart businessId={primaryBusiness.id} dateRange={dateRange} token={token} />
    </div>
  );
}
