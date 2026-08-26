"use client";

/**
 * Revenue & Profit chart.
 *
 * Wraps recharts around GET /businesses/{id}/analytics/timeseries. Takes
 * the same DateRangeValue the rest of the dashboard uses, so it stays in
 * sync with the page-level DateRangePicker -- no local range state here.
 * Granularity (day/week/month) is chosen locally since it's a chart-only
 * concern the summary cards don't need.
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
  Legend,
} from "recharts";
import { fetchAnalyticsTimeseries } from "@/lib/analytics";
import { ApiError } from "@/lib/api";
import type { DateRangeValue, TimeseriesPoint } from "@/types";
import styles from "./RevenueProfitChart.module.css";

type Granularity = "day" | "week" | "month";

interface Props {
  businessId: string;
  dateRange: DateRangeValue;
  token: string;
}

const GRANULARITIES: { label: string; value: Granularity }[] = [
  { label: "Day", value: "day" },
  { label: "Week", value: "week" },
  { label: "Month", value: "month" },
];

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function formatCurrencyShort(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `${value < 0 ? "-" : ""}$${(Math.abs(value) / 1000).toFixed(1)}k`;
  }
  return currencyFormatter.format(value);
}

function formatAxisDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

interface ChartRow {
  period_start: string;
  revenue: number;
  gross_profit: number;
}

function toChartRows(points: TimeseriesPoint[]): ChartRow[] {
  return points.map((p) => ({
    period_start: p.period_start,
    revenue: Number(p.revenue),
    gross_profit: Number(p.total_cost) >= 0 ? Number(p.revenue) - Number(p.total_cost) : Number(p.revenue),
  }));
}

export default function RevenueProfitChart({ businessId, dateRange, token }: Props) {
  const [granularity, setGranularity] = useState<Granularity>("day");
  const [rows, setRows] = useState<ChartRow[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchAnalyticsTimeseries(businessId, dateRange, granularity, token)
      .then((data) => {
        if (!cancelled) setRows(toChartRows(data.points));
      })
      .catch((err) => {
        if (!cancelled) {
          setRows([]);
          setError(err instanceof ApiError ? err.message : "Could not load chart data.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [businessId, dateRange, granularity, token]);

  const hasData = rows.length > 0 && rows.some((r) => r.revenue !== 0 || r.gross_profit !== 0);

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Revenue &amp; Profit</h2>
        <div className={styles.granularityGroup} role="group" aria-label="Chart granularity">
          {GRANULARITIES.map((g) => (
            <button
              key={g.value}
              type="button"
              className={`${styles.granularityButton} ${
                granularity === g.value ? styles.granularityButtonActive : ""
              }`}
              onClick={() => setGranularity(g.value)}
            >
              {g.label}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.legendKey}>
        <span className={styles.legendItem}>
          <span className={styles.swatchRevenue} /> Revenue
        </span>
        <span className={styles.legendItem}>
          <span className={styles.swatchProfit} /> Gross profit
        </span>
      </div>

      <div className={styles.chartArea}>
        {isLoading ? (
          <div className={styles.placeholder}>Loading…</div>
        ) : error ? (
          <div className={styles.placeholder}>{error}</div>
        ) : !hasData ? (
          <div className={styles.placeholder}>No data for this range yet</div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#1f2430" vertical={false} />
              <XAxis
                dataKey="period_start"
                tickFormatter={formatAxisDate}
                stroke="#8a92a6"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: "#1f2430" }}
              />
              <YAxis
                tickFormatter={(v) => formatCurrencyShort(Number(v))}
                stroke="#8a92a6"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                width={56}
              />
              <Tooltip
                contentStyle={{
                  background: "#151922",
                  border: "1px solid #2a2f3a",
                  borderRadius: 8,
                  fontSize: 13,
                }}
                labelFormatter={(label) => formatAxisDate(String(label))}
                formatter={(value: number, name: string) => [
                  currencyFormatter.format(value),
                  name === "revenue" ? "Revenue" : "Gross profit",
                ]}
              />
              <Legend wrapperStyle={{ display: "none" }} />
              <Bar dataKey="revenue" name="revenue" fill="#4f7cff" radius={[4, 4, 0, 0]} maxBarSize={36} />
              <Line
                dataKey="gross_profit"
                name="gross_profit"
                type="monotone"
                stroke="#33d69f"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
