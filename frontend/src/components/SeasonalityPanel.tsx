"use client";

/**
 * Day-of-week seasonality.
 *
 * The other classic Excel/Power BI report output the app lacked: not
 * "how did revenue trend over time" (already covered by the main
 * chart) but "which weekdays actually perform best" -- a pattern that
 * only shows up once you bucket by day-of-week and average across
 * however many of each weekday fall in the range.
 *
 * Self-fetching, but reuses the *daily* timeseries endpoint rather
 * than a new one -- granularity=day gives one point per calendar day,
 * which is exactly what day-of-week bucketing needs. No new backend
 * work for this batch either.
 */
import { useEffect, useMemo, useState } from "react";
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { fetchAnalyticsTimeseries } from "@/lib/analytics";
import { ApiError } from "@/lib/api";
import type { DateRangeValue, TimeseriesPoint } from "@/types";
import styles from "./SeasonalityPanel.module.css";

interface Props {
  businessId: string;
  dateRange: DateRangeValue;
  token: string;
}

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

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

interface WeekdayBucket {
  label: string;
  avgRevenue: number;
  avgProfit: number;
  dayCount: number;
}

/** Buckets daily points by weekday (Mon-first) and averages each --
 * "average Saturday" rather than "sum of all Saturdays", since a range
 * rarely contains a whole number of each weekday and a sum would just
 * favor whichever weekday happened to occur one extra time. */
function bucketByWeekday(points: TimeseriesPoint[]): WeekdayBucket[] {
  const sums = WEEKDAY_LABELS.map(() => ({ revenue: 0, profit: 0, count: 0 }));

  for (const point of points) {
    const date = new Date(`${point.period_start}T00:00:00Z`);
    if (Number.isNaN(date.getTime())) continue;
    const mondayFirstIndex = (date.getUTCDay() + 6) % 7;
    sums[mondayFirstIndex].revenue += Number(point.revenue);
    sums[mondayFirstIndex].profit += Number(point.gross_profit);
    sums[mondayFirstIndex].count += 1;
  }

  return WEEKDAY_LABELS.map((label, i) => ({
    label,
    avgRevenue: sums[i].count > 0 ? sums[i].revenue / sums[i].count : 0,
    avgProfit: sums[i].count > 0 ? sums[i].profit / sums[i].count : 0,
    dayCount: sums[i].count,
  }));
}

export default function SeasonalityPanel({ businessId, dateRange, token }: Props) {
  const [points, setPoints] = useState<TimeseriesPoint[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchAnalyticsTimeseries(businessId, dateRange, "day", token)
      .then((data) => {
        if (!cancelled) setPoints(data.points);
      })
      .catch((err) => {
        if (!cancelled) {
          setPoints([]);
          setError(err instanceof ApiError ? err.message : "Could not load this analysis.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [businessId, dateRange, token]);

  const buckets = useMemo(() => bucketByWeekday(points), [points]);
  const trackedBuckets = buckets.filter((b) => b.dayCount > 0);
  const hasData = trackedBuckets.some((b) => b.avgRevenue !== 0);

  const overallAvg =
    trackedBuckets.length > 0
      ? trackedBuckets.reduce((sum, b) => sum + b.avgRevenue, 0) / trackedBuckets.length
      : 0;

  let best: WeekdayBucket | null = null;
  let worst: WeekdayBucket | null = null;
  if (hasData) {
    // Need at least 2 distinct weekdays actually populated for a
    // "best vs worst" comparison to mean anything.
    const populated = trackedBuckets.filter((b) => b.dayCount > 0);
    if (populated.length >= 2) {
      best = populated.reduce((a, b) => (b.avgRevenue > a.avgRevenue ? b : a));
      worst = populated.reduce((a, b) => (b.avgRevenue < a.avgRevenue ? b : a));
    }
  }

  const maxAvg = Math.max(...buckets.map((b) => b.avgRevenue), 1);

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.iconWrap}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
            <path d="M3 9h18M8 3v4M16 3v4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </div>
        <div>
          <h2 className={styles.title}>Weekly pattern</h2>
          <p className={styles.description}>Average revenue by day of week</p>
        </div>
      </div>

      {isLoading ? (
        <div className={styles.placeholder}>Loading…</div>
      ) : error ? (
        <div className={styles.placeholder}>{error}</div>
      ) : !hasData ? (
        <div className={styles.placeholder}>No revenue in this range yet</div>
      ) : (
        <>
          {best && worst && best.label !== worst.label && (
            <p className={styles.headline}>
              <strong>{best.label}s</strong> are your best day, averaging{" "}
              <strong>{currencyFormatter.format(best.avgRevenue)}</strong>
              {overallAvg > 0 && (
                <> ({Math.round(((best.avgRevenue - overallAvg) / overallAvg) * 100)}% above average)</>
              )}
              . <strong>{worst.label}s</strong> lag behind at{" "}
              {currencyFormatter.format(worst.avgRevenue)}.
            </p>
          )}
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={buckets} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--surface-border)" vertical={false} />
              <XAxis
                dataKey="label"
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
              <Tooltip
                contentStyle={{
                  background: "var(--surface)",
                  border: "1px solid var(--surface-border)",
                  borderRadius: 8,
                  fontSize: 13,
                }}
                formatter={(value: number, _name: string, item) => [
                  currencyFormatter.format(value),
                  `Avg. revenue (${item.payload.dayCount} ${item.payload.dayCount === 1 ? "day" : "days"})`,
                ]}
              />
              <Bar dataKey="avgRevenue" radius={[4, 4, 0, 0]} maxBarSize={44}>
                {buckets.map((bucket) => (
                  <Cell
                    key={bucket.label}
                    fill="var(--gold)"
                    fillOpacity={bucket.dayCount === 0 ? 0.15 : Math.max(bucket.avgRevenue / maxAvg, 0.25)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  );
}
