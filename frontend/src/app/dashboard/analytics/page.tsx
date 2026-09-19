"use client";

/**
 * Analytics page -- the deep-dive BI surface (Overview stays glanceable;
 * this is where someone actually analyzes the business).
 *
 * Batch 1 of the analysis-side redesign: an executive KPI strip (the
 * standard "scorecard row" every Excel/Power BI report leads with) sits
 * above the existing revenue/profit trend chart. Reuses MetricCard --
 * same component, same vs-previous-period math (via lib/analytics's
 * previousPeriodRange/percentChange, shared with Overview so both pages
 * define "previous period" identically) -- so this reads as more of the
 * same dashboard, not a bolted-on second design.
 *
 * Later batches (breakdown/pivot, Pareto, seasonality, variance table)
 * land as additional sections below the trend chart, each independently
 * addable without touching this one.
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { fetchAnalyticsSummary, fetchAnalyticsTimeseries, percentChange, previousPeriodRange } from "@/lib/analytics";
import { ApiError } from "@/lib/api";
import type { AnalyticsSummary, DateRangeValue } from "@/types";
import DateRangePicker from "@/components/DateRangePicker";
import MetricCard from "@/components/MetricCard";
import RevenueProfitChart from "@/components/RevenueProfitChart";
import AnalyticsBreakdownPanel from "@/components/AnalyticsBreakdownPanel";
import ParetoAnalysisPanel from "@/components/ParetoAnalysisPanel";
import ComingSoon from "@/components/ComingSoon";
import styles from "./analytics.module.css";

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 2,
});

const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
});

function formatCurrency(value: string): string {
  return currencyFormatter.format(Number(value));
}

function formatPercent(value: string): string {
  return `${numberFormatter.format(Number(value))}%`;
}

function formatNumber(value: string | number): string {
  return numberFormatter.format(Number(value));
}

export default function AnalyticsPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();
  const [dateRange, setDateRange] = useState<DateRangeValue>({ range: "30d" });

  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [previousSummary, setPreviousSummary] = useState<AnalyticsSummary | null>(null);
  const [sparklines, setSparklines] = useState<{ revenue: number[]; profit: number[]; margin: number[] }>({
    revenue: [],
    profit: [],
    margin: [],
  });
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !primaryBusiness) return;

    let cancelled = false;
    setIsLoadingSummary(true);
    setSummaryError(null);

    fetchAnalyticsSummary(primaryBusiness.id, dateRange, token)
      .then(async (data) => {
        if (cancelled) return;
        setSummary(data);

        // Comparison period and sparkline both derive from this same
        // resolved summary (its actual start_date/end_date), so they
        // always describe the exact range shown -- same pattern as
        // Overview's KPI cards.
        const prevRange = previousPeriodRange(data.start_date, data.end_date);
        const [previous, timeseries] = await Promise.all([
          fetchAnalyticsSummary(primaryBusiness.id, { range: "custom", ...prevRange }, token).catch(
            () => null
          ),
          fetchAnalyticsTimeseries(primaryBusiness.id, dateRange, "day", token).catch(() => null),
        ]);
        if (cancelled) return;

        setPreviousSummary(previous);
        if (timeseries) {
          setSparklines({
            revenue: timeseries.points.map((p) => Number(p.revenue)),
            profit: timeseries.points.map((p) => Number(p.gross_profit)),
            margin: timeseries.points.map((p) =>
              Number(p.revenue) > 0 ? (Number(p.gross_profit) / Number(p.revenue)) * 100 : 0
            ),
          });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setSummary(null);
          setSummaryError(err instanceof ApiError ? err.message : "Could not load analytics.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoadingSummary(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token, primaryBusiness, dateRange]);

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

  const hasData = !!summary && summary.transaction_count > 0;
  const emptyText = isLoadingSummary
    ? "Loading…"
    : summaryError
      ? "Couldn't load"
      : "No transactions yet";

  const revenueChange =
    summary && previousSummary ? percentChange(Number(summary.revenue), Number(previousSummary.revenue)) : null;
  const profitChange =
    summary && previousSummary
      ? percentChange(Number(summary.gross_profit), Number(previousSummary.gross_profit))
      : null;
  const marginChange =
    summary && previousSummary ? Number(summary.profit_margin) - Number(previousSummary.profit_margin) : null;
  const aovChange =
    summary && previousSummary
      ? percentChange(Number(summary.average_transaction_value), Number(previousSummary.average_transaction_value))
      : null;
  const transactionsChange =
    summary && previousSummary
      ? percentChange(summary.transaction_count, previousSummary.transaction_count)
      : null;
  const unitsChange =
    summary && previousSummary
      ? percentChange(Number(summary.units_sold), Number(previousSummary.units_sold))
      : null;

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h1>Analytics</h1>
          <p className={styles.subtitle}>The full breakdown behind the Overview numbers.</p>
        </div>
        <DateRangePicker value={dateRange} onChange={setDateRange} />
      </div>

      <div className={styles.kpiGrid}>
        <MetricCard
          label="Revenue"
          icon="revenue"
          accent="gold"
          isLoading={isLoadingSummary}
          isEmpty={!hasData}
          emptyText={emptyText}
          value={summary ? formatCurrency(summary.revenue) : undefined}
          changePercent={revenueChange}
          changeLabel="vs previous period"
          sparklineValues={sparklines.revenue}
        />
        <MetricCard
          label="Gross Profit"
          icon="profit"
          accent="leaf"
          isLoading={isLoadingSummary}
          isEmpty={!hasData}
          emptyText={emptyText}
          value={summary ? formatCurrency(summary.gross_profit) : undefined}
          changePercent={profitChange}
          changeLabel="vs previous period"
          sparklineValues={sparklines.profit}
        />
        <MetricCard
          label="Profit Margin"
          icon="margin"
          accent="purple"
          isLoading={isLoadingSummary}
          isEmpty={!hasData}
          emptyText={emptyText}
          value={summary ? formatPercent(summary.profit_margin) : undefined}
          changePercent={marginChange}
          changeLabel="vs previous period"
          sparklineValues={sparklines.margin}
        />
        <MetricCard
          label="Avg. Transaction Value"
          icon="average"
          accent="blue"
          isLoading={isLoadingSummary}
          isEmpty={!hasData}
          emptyText={emptyText}
          value={summary ? formatCurrency(summary.average_transaction_value) : undefined}
          changePercent={aovChange}
          changeLabel="vs previous period"
        />
        <MetricCard
          label="Transactions"
          icon="transactions"
          accent="neutral"
          isLoading={isLoadingSummary}
          isEmpty={!hasData}
          emptyText={isLoadingSummary ? "Loading…" : summaryError ? "Couldn't load" : "0 recorded"}
          value={summary ? formatNumber(summary.transaction_count) : undefined}
          changePercent={transactionsChange}
          changeLabel="vs previous period"
        />
        <MetricCard
          label="Units Sold"
          icon="products"
          accent="gold"
          isLoading={isLoadingSummary}
          isEmpty={!hasData}
          emptyText={isLoadingSummary ? "Loading…" : summaryError ? "Couldn't load" : "0 sold"}
          value={summary ? formatNumber(summary.units_sold) : undefined}
          changePercent={unitsChange}
          changeLabel="vs previous period"
        />
      </div>

      <div className={styles.chartSection}>
        <RevenueProfitChart businessId={primaryBusiness.id} dateRange={dateRange} token={token} />
      </div>

      <div className={styles.breakdownSection}>
        <AnalyticsBreakdownPanel businessId={primaryBusiness.id} dateRange={dateRange} token={token} />
      </div>

      <div className={styles.paretoSection}>
        <ParetoAnalysisPanel businessId={primaryBusiness.id} dateRange={dateRange} token={token} />
      </div>

      {summaryError && <p className={styles.error}>{summaryError}</p>}
    </div>
  );
}
