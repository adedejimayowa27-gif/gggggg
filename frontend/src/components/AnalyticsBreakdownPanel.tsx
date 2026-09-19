"use client";

/**
 * Category / customer / payment-method breakdown -- the standard
 * Power BI "matrix" visual: pick a dimension, see revenue ranked and
 * contextualized against the total.
 *
 * Self-fetching (same pattern as RevenueProfitChart): owns its own
 * groupBy tab state and re-fetches GET .../analytics/breakdown whenever
 * the tab or the page's date range changes. Row treatment (rank badge,
 * magnitude bar, skeleton/empty states) mirrors ProductRankingCard so
 * this reads as the same design language, not a new one -- the one
 * addition is the "isUntracked" state for when a business has simply
 * never recorded a dimension (e.g. no payment method logged on any
 * transaction), distinct from "no transactions in this range."
 */
import { useEffect, useState } from "react";
import { fetchAnalyticsBreakdown } from "@/lib/analytics";
import { ApiError } from "@/lib/api";
import type { AnalyticsBreakdown, DateRangeValue } from "@/types";
import styles from "./AnalyticsBreakdownPanel.module.css";

type GroupBy = "category" | "customer" | "payment_method";

interface Props {
  businessId: string;
  dateRange: DateRangeValue;
  token: string;
}

const TABS: { key: GroupBy; label: string }[] = [
  { key: "category", label: "Category" },
  { key: "customer", label: "Customer" },
  { key: "payment_method", label: "Payment method" },
];

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 2,
});

const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

function formatCurrency(value: string): string {
  return currencyFormatter.format(Number(value));
}

function TagIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 2l9 9-9 9-9-9V2h9z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <circle cx="7.5" cy="7.5" r="1.5" fill="currentColor" />
    </svg>
  );
}

export default function AnalyticsBreakdownPanel({ businessId, dateRange, token }: Props) {
  const [groupBy, setGroupBy] = useState<GroupBy>("category");
  const [data, setData] = useState<AnalyticsBreakdown | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchAnalyticsBreakdown(businessId, dateRange, groupBy, token, 8)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setData(null);
          setError(err instanceof ApiError ? err.message : "Could not load this breakdown.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [businessId, dateRange, groupBy, token]);

  const totalRevenue = data ? data.items.reduce((sum, item) => sum + Number(item.revenue), 0) : 0;
  const maxRevenue = data && data.items.length > 0 ? Math.max(...data.items.map((i) => Number(i.revenue)), 1) : 1;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.iconWrap}>
            <TagIcon />
          </div>
          <div>
            <h2 className={styles.title}>Revenue breakdown</h2>
            <p className={styles.description}>Where revenue is actually coming from</p>
          </div>
        </div>
        <div className={styles.tabs}>
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`${styles.tab} ${groupBy === tab.key ? styles.tabActive : ""}`}
              onClick={() => setGroupBy(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className={styles.skeletonList}>
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className={styles.skeletonRow}>
              <span className={styles.skeletonBadge} />
              <span className={styles.skeletonLine} />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className={styles.stateBox}>
          <p className={styles.stateTitle}>Couldn&rsquo;t load this breakdown</p>
          <p className={styles.stateBody}>{error}</p>
        </div>
      ) : data && !data.has_data ? (
        <div className={styles.stateBox}>
          <p className={styles.stateTitle}>Not tracked yet</p>
          <p className={styles.stateBody}>
            None of your transactions have a {TABS.find((t) => t.key === groupBy)?.label.toLowerCase()} recorded,
            so there&rsquo;s nothing to break down here yet.
          </p>
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className={styles.stateBox}>
          <p className={styles.stateTitle}>Nothing here yet</p>
          <p className={styles.stateBody}>No transactions in this range.</p>
        </div>
      ) : (
        <ol className={styles.list}>
          {data.items.map((item, index) => {
            const share = totalRevenue > 0 ? (Number(item.revenue) / totalRevenue) * 100 : 0;
            const barWidth = Math.max((Number(item.revenue) / maxRevenue) * 100, 3);
            return (
              <li key={item.group} className={styles.row}>
                <div className={styles.rowTop}>
                  <span className={styles.badge}>{index + 1}</span>
                  <div className={styles.rowMain}>
                    <span className={styles.groupName}>{item.group}</span>
                    <span className={styles.rowSub}>
                      {numberFormatter.format(share)}% of revenue · {item.transaction_count} transactions
                    </span>
                  </div>
                  <div className={styles.rowMetric}>
                    <span className={styles.metricValue}>{formatCurrency(item.revenue)}</span>
                    <span className={styles.metricLabel}>revenue</span>
                  </div>
                </div>
                <div className={styles.barTrack}>
                  <div className={styles.barFill} style={{ width: `${barWidth}%` }} />
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
