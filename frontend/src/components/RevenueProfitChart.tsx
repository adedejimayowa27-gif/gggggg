"use client";

/**
 * Revenue & Profit chart.
 *
 * Wraps recharts around GET /businesses/{id}/analytics/timeseries. Takes
 * the same DateRangeValue the rest of the dashboard uses, so it stays in
 * sync with the page-level DateRangePicker -- no local range state here.
 * Granularity (day/week/month) is chosen locally since it's a chart-only
 * concern the summary cards don't need.
 *
 * Visual + functional pass: gradient-filled bars and a gradient area
 * under the profit line (instead of flat fills, which made the two
 * series hard to tell apart whenever profit tracked close to revenue --
 * exactly the case in real data, where a healthy business's profit
 * line often sits just under its revenue bars). A computed stat row
 * above the chart (total revenue, total profit, average margin, best
 * day) surfaces the insight a raw bar chart makes someone hunt for
 * themselves. The tooltip now shows margin % alongside the two raw
 * values, since "how much of this bar was actually profit" is the
 * natural next question a revenue/profit chart invites.
 */
import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  TooltipProps,
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
  /** Defaults preserve the exact heading the Analytics page already
   * shows -- only the Overview page (Batch 6) passes something
   * different, so nothing about the existing Analytics usage changes. */
  title?: string;
  /** The period's total transaction count, if the caller already has it
   * (the Overview page does, from its own summary fetch) -- shown as a
   * plain supplementary stat rather than plotted on the chart, since
   * the timeseries endpoint this chart is built on doesn't return a
   * per-period transaction count to actually chart truthfully. */
  transactionCount?: number;
}

const GRANULARITIES: { label: string; value: Granularity }[] = [
  { label: "Day", value: "day" },
  { label: "Week", value: "week" },
  { label: "Month", value: "month" },
];

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 0,
});

const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

function formatCurrencyShort(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `${value < 0 ? "-" : ""}₦${(Math.abs(value) / 1000).toFixed(1)}k`;
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

function CustomTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  const revenue = Number(payload.find((p) => p.dataKey === "revenue")?.value ?? 0);
  const profit = Number(payload.find((p) => p.dataKey === "gross_profit")?.value ?? 0);
  const margin = revenue !== 0 ? (profit / revenue) * 100 : 0;
  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipDate}>{formatAxisDate(String(label))}</div>
      <div className={styles.tooltipRow}>
        <span className={styles.tooltipDotRevenue} />
        <span className={styles.tooltipLabel}>Revenue</span>
        <span className={styles.tooltipValue}>{currencyFormatter.format(revenue)}</span>
      </div>
      <div className={styles.tooltipRow}>
        <span className={styles.tooltipDotProfit} />
        <span className={styles.tooltipLabel}>Gross profit</span>
        <span className={styles.tooltipValue}>{currencyFormatter.format(profit)}</span>
      </div>
      <div className={styles.tooltipDivider} />
      <div className={styles.tooltipRow}>
        <span className={styles.tooltipLabel}>Margin</span>
        <span className={styles.tooltipValue}>{numberFormatter.format(margin)}%</span>
      </div>
    </div>
  );
}

export default function RevenueProfitChart({
  businessId,
  dateRange,
  token,
  title = "Revenue & Profit",
  transactionCount,
}: Props) {
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

  const stats = useMemo(() => {
    if (!hasData) return null;
    const totalRevenue = rows.reduce((sum, r) => sum + r.revenue, 0);
    const totalProfit = rows.reduce((sum, r) => sum + r.gross_profit, 0);
    const avgMargin = totalRevenue !== 0 ? (totalProfit / totalRevenue) * 100 : 0;
    const bestRow = rows.reduce((best, r) => (r.revenue > best.revenue ? r : best), rows[0]);
    return { totalRevenue, totalProfit, avgMargin, bestRow };
  }, [rows, hasData]);

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{title}</h2>
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
        {typeof transactionCount === "number" && (
          <span className={styles.transactionStat}>
            <strong>{transactionCount.toLocaleString()}</strong> transactions this period
          </span>
        )}
      </div>

      {stats && (
        <div className={styles.statsRow}>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>Total revenue</span>
            <span className={styles.statValue}>{currencyFormatter.format(stats.totalRevenue)}</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>Total profit</span>
            <span className={styles.statValue}>{currencyFormatter.format(stats.totalProfit)}</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>Avg. margin</span>
            <span className={styles.statValue}>{numberFormatter.format(stats.avgMargin)}%</span>
          </div>
          <div className={`${styles.statItem} ${styles.statItemBest}`}>
            <span className={styles.statLabel}>Best day</span>
            <span className={styles.statValue}>
              {formatAxisDate(stats.bestRow.period_start)} · {formatCurrencyShort(stats.bestRow.revenue)}
            </span>
          </div>
        </div>
      )}

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
              <defs>
                <linearGradient id="revenueBarGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--gold)" stopOpacity={1} />
                  <stop offset="100%" stopColor="var(--gold)" stopOpacity={0.45} />
                </linearGradient>
                <linearGradient id="profitAreaGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--leaf)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--leaf)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--surface-border)" vertical={false} />
              <XAxis
                dataKey="period_start"
                tickFormatter={formatAxisDate}
                stroke="var(--sage)"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: "var(--surface-border)" }}
              />
              <YAxis
                tickFormatter={(v) => formatCurrencyShort(Number(v))}
                stroke="var(--sage)"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                width={56}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: "var(--surface-active)", opacity: 0.4 }} />
              <Bar
                dataKey="revenue"
                name="revenue"
                fill="url(#revenueBarGradient)"
                radius={[5, 5, 0, 0]}
                maxBarSize={36}
              />
              <Area
                dataKey="gross_profit"
                name="gross_profit"
                type="monotone"
                stroke="var(--leaf)"
                strokeWidth={2.5}
                fill="url(#profitAreaGradient)"
                dot={false}
                activeDot={{ r: 5, stroke: "var(--paper)", strokeWidth: 2 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
