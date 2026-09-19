"use client";

/**
 * Pareto (80/20) analysis.
 *
 * The one classic Excel/Power BI output the app didn't have at all:
 * of everything driving revenue in a dimension, how concentrated is
 * it? Reuses the same GET .../analytics/breakdown endpoint as
 * AnalyticsBreakdownPanel (Batch 2) -- same data, different lens: here
 * it's read as a cumulative curve against an 80% reference line, with
 * the "how concentrated" answer spelled out as a plain-language
 * headline instead of left for someone to read off the chart.
 *
 * Self-fetching with its own groupBy tabs, same as AnalyticsBreakdownPanel,
 * rather than sharing that panel's state -- someone might reasonably
 * want the breakdown on "Category" while checking concentration on
 * "Customer" at the same time.
 *
 * Accuracy note: the breakdown endpoint caps at 100 groups. For
 * category/payment method that's effectively everything for any real
 * business; for customer lists past 100 the cumulative % is computed
 * against the top 100's own total, not the true grand total -- a
 * reasonable approximation, not one this panel calls out inline (it'd
 * be noise for the overwhelming majority of businesses under that
 * threshold).
 */
import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { fetchAnalyticsBreakdown } from "@/lib/analytics";
import { ApiError } from "@/lib/api";
import type { AnalyticsBreakdown, DateRangeValue } from "@/types";
import styles from "./ParetoAnalysisPanel.module.css";

type GroupBy = "category" | "customer" | "payment_method";

interface Props {
  businessId: string;
  dateRange: DateRangeValue;
  token: string;
}

const TABS: { key: GroupBy; label: string; nounPlural: string }[] = [
  { key: "category", label: "Category", nounPlural: "categories" },
  { key: "customer", label: "Customer", nounPlural: "customers" },
  { key: "payment_method", label: "Payment method", nounPlural: "payment methods" },
];

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 0,
});

function formatCurrencyShort(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `${value < 0 ? "-" : ""}₦${(Math.abs(value) / 1000).toFixed(1)}k`;
  }
  return currencyFormatter.format(value);
}

interface ChartRow {
  group: string;
  revenue: number;
  cumulativePct: number;
}

function buildRows(data: AnalyticsBreakdown): ChartRow[] {
  const total = data.items.reduce((sum, item) => sum + Number(item.revenue), 0);
  let running = 0;
  return data.items.map((item) => {
    running += Number(item.revenue);
    return {
      group: item.group,
      revenue: Number(item.revenue),
      cumulativePct: total > 0 ? (running / total) * 100 : 0,
    };
  });
}

/** How many top-ranked groups it takes to reach 80% of revenue, and
 * what share of the whole population that represents -- the headline
 * number a Pareto chart exists to answer. */
function paretoBreakpoint(rows: ChartRow[]): { count: number; pctOfGroups: number } | null {
  if (rows.length === 0) return null;
  const index = rows.findIndex((r) => r.cumulativePct >= 80);
  const count = index === -1 ? rows.length : index + 1;
  return { count, pctOfGroups: (count / rows.length) * 100 };
}

export default function ParetoAnalysisPanel({ businessId, dateRange, token }: Props) {
  const [groupBy, setGroupBy] = useState<GroupBy>("customer");
  const [rows, setRows] = useState<ChartRow[]>([]);
  const [hasData, setHasData] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchAnalyticsBreakdown(businessId, dateRange, groupBy, token, 100)
      .then((data) => {
        if (cancelled) return;
        setHasData(data.has_data);
        setRows(buildRows(data));
      })
      .catch((err) => {
        if (!cancelled) {
          setRows([]);
          setError(err instanceof ApiError ? err.message : "Could not load this analysis.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [businessId, dateRange, groupBy, token]);

  const activeTab = TABS.find((t) => t.key === groupBy)!;
  const breakpoint = paretoBreakpoint(rows);
  const chartHasRevenue = rows.some((r) => r.revenue !== 0);

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.iconWrap}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M4 20V12M11 20V4M18 20v-8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              <path
                d="M3 16c4-1 7-6 9-8s5.5-3 9-1"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeDasharray="1 3.5"
              />
            </svg>
          </div>
          <div>
            <h2 className={styles.title}>Concentration analysis</h2>
            <p className={styles.description}>How much of revenue rides on how few {activeTab.nounPlural}</p>
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
        <div className={styles.placeholder}>Loading…</div>
      ) : error ? (
        <div className={styles.placeholder}>{error}</div>
      ) : !hasData ? (
        <div className={styles.placeholder}>
          None of your transactions have a {activeTab.label.toLowerCase()} recorded yet.
        </div>
      ) : !chartHasRevenue ? (
        <div className={styles.placeholder}>No revenue in this range yet</div>
      ) : (
        <>
          {breakpoint && (
            <p className={styles.headline}>
              <strong>
                {Math.min(Math.round(breakpoint.pctOfGroups), 100)}% of {activeTab.nounPlural}
              </strong>{" "}
              ({breakpoint.count} of {rows.length}) drive{" "}
              <strong>80%</strong> of revenue in this range.
            </p>
          )}
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--surface-border)" vertical={false} />
              <XAxis
                dataKey="group"
                stroke="var(--sage)"
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: "var(--surface-border)" }}
                interval={rows.length > 12 ? Math.ceil(rows.length / 12) - 1 : 0}
                tickFormatter={(v: string) => (v.length > 10 ? `${v.slice(0, 9)}…` : v)}
              />
              <YAxis
                yAxisId="revenue"
                tickFormatter={(v) => formatCurrencyShort(Number(v))}
                stroke="var(--sage)"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                width={56}
              />
              <YAxis
                yAxisId="pct"
                orientation="right"
                domain={[0, 100]}
                tickFormatter={(v) => `${v}%`}
                stroke="var(--sage)"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                width={44}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--surface)",
                  border: "1px solid var(--surface-border)",
                  borderRadius: 8,
                  fontSize: 13,
                }}
                formatter={(value: number, name: string) =>
                  name === "revenue"
                    ? [currencyFormatter.format(value), "Revenue"]
                    : [`${value.toFixed(1)}%`, "Cumulative"]
                }
              />
              <ReferenceLine
                yAxisId="pct"
                y={80}
                stroke="var(--clay)"
                strokeDasharray="4 4"
                label={{ value: "80%", position: "right", fill: "var(--clay)", fontSize: 11 }}
              />
              <Bar yAxisId="revenue" dataKey="revenue" name="revenue" fill="var(--gold)" radius={[3, 3, 0, 0]} maxBarSize={28} />
              <Line
                yAxisId="pct"
                dataKey="cumulativePct"
                name="cumulativePct"
                type="monotone"
                stroke="var(--viz-purple)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  );
}
