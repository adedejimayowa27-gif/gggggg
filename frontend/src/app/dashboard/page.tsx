"use client";

import { useEffect, useState, FormEvent } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { apiFetch, ApiError } from "@/lib/api";
import { fetchAnalyticsSummary, fetchAnalyticsTimeseries } from "@/lib/analytics";
import type { AnalyticsSummary, Business, DateRangeValue } from "@/types";
import MetricCard from "@/components/MetricCard";
import DateRangePicker from "@/components/DateRangePicker";
import AlertsPanel from "@/components/AlertsPanel";
import AIBusinessBrief from "@/components/AIBusinessBrief";
import RevenueProfitChart from "@/components/RevenueProfitChart";
import AIAssistantPanel from "@/components/AIAssistantPanel";
import QuickActionsPanel from "@/components/QuickActionsPanel";
import TopProductsPanel from "@/components/TopProductsPanel";
import RecentTransactionsPanel from "@/components/RecentTransactionsPanel";
import styles from "./overview.module.css";

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

/** A same-length period immediately preceding the current one, so
 * "vs previous period" compares like-for-like (e.g. a 30-day window
 * against the 30 days before it) rather than an arbitrary lookback. */
function previousPeriodRange(startDate: string, endDate: string): { start_date: string; end_date: string } {
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  const durationMs = end.getTime() - start.getTime();
  const prevEnd = new Date(start.getTime() - 24 * 60 * 60 * 1000);
  const prevStart = new Date(prevEnd.getTime() - durationMs);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { start_date: iso(prevStart), end_date: iso(prevEnd) };
}

/** Relative percentage change, or null when there's no honest baseline
 * to compare against (previous period had literally zero) -- shown as
 * no comparison at all rather than a misleading "+100%"/"-100%"/"∞". */
function percentChange(current: number, previous: number): number | null {
  if (previous === 0) return null;
  return ((current - previous) / previous) * 100;
}

export default function OverviewPage() {
  const { token } = useAuth();
  const { businesses, primaryBusiness, isLoadingBusinesses, refreshBusinesses, selectBusiness } = useDashboard();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

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
        // always describe the exact range shown, not a hardcoded
        // assumption about what the selected preset means in days.
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

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setFormError(null);
    setIsCreating(true);
    try {
      const created = await apiFetch<Business>("/businesses", {
        method: "POST",
        authToken: token,
        body: JSON.stringify({ name, industry: industry || undefined }),
      });
      setName("");
      setIndustry("");
      setShowCreateForm(false);
      await refreshBusinesses();
      selectBusiness(created.id);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create business.");
    } finally {
      setIsCreating(false);
    }
  };

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  // No business yet: this is the only state where the create-business flow
  // is front and center. Preserves the Step 1 capability without cluttering
  // the metrics dashboard once a business exists.
  if (!primaryBusiness) {
    return (
      <div className={styles.emptyBusinessWrap}>
        <h2>Create your business</h2>
        <p>You need a business before you can see your dashboard.</p>
        <form onSubmit={handleCreate} className={styles.form}>
          <input
            type="text"
            placeholder="Business name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={styles.input}
          />
          <input
            type="text"
            placeholder="Industry (optional)"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className={styles.input}
          />
          <button type="submit" disabled={isCreating} className={styles.submitButton}>
            {isCreating ? "Creating…" : "Create business"}
          </button>
        </form>
        {formError && <p className={styles.error}>{formError}</p>}
      </div>
    );
  }

  // A business exists but the summary either hasn't loaded yet or came
  // back with nothing in range -- both render the cards' built-in empty
  // state rather than a stale/blank number.
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
  const transactionsChange =
    summary && previousSummary
      ? percentChange(summary.transaction_count, previousSummary.transaction_count)
      : null;

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h1>{primaryBusiness.name}</h1>
          {primaryBusiness.industry && (
            <span className={styles.industryChip}>{primaryBusiness.industry}</span>
          )}
        </div>
        <div className={styles.headerControls}>
          <DateRangePicker value={dateRange} onChange={setDateRange} />
          <button className={styles.newBusinessButton} onClick={() => setShowCreateForm((s) => !s)}>
            {showCreateForm ? "Cancel" : "+ New business"}
          </button>
        </div>
      </div>

      {showCreateForm && (
        <div className={styles.emptyBusinessWrap} style={{ marginBottom: "2rem", maxWidth: 360 }}>
          <form onSubmit={handleCreate} className={styles.form}>
            <input
              type="text"
              placeholder="Business name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={styles.input}
            />
            <input
              type="text"
              placeholder="Industry (optional)"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className={styles.input}
            />
            <button type="submit" disabled={isCreating} className={styles.submitButton}>
              {isCreating ? "Creating…" : "Create business"}
            </button>
          </form>
          {formError && <p className={styles.error}>{formError}</p>}
        </div>
      )}

      {/* Fixed from before: this used to render unconditionally
          regardless of whether the business actually had data yet,
          showing "No transaction data" even on a business with months
          of real transactions. Now gated behind !hasData, and rewritten
          to the brief's polished, non-error-looking empty state. */}
      {!isLoadingSummary && !hasData && (
        <div className={styles.uploadSection}>
          <div className={styles.uploadText}>
            <h2>Unlock your business intelligence</h2>
            <p>
              Connect your sales or transaction data to start seeing revenue trends, profit
              analysis, forecasts, and AI insights.
            </p>
          </div>
          <Link href="/dashboard/transactions" className={styles.uploadButton}>
            + Import transactions
          </Link>
        </div>
      )}

      {token && <AlertsPanel businessId={primaryBusiness.id} token={token} compact />}

      <div className={styles.cardsGrid}>
        <MetricCard
          label="Revenue"
          icon="revenue"
          accent="gold"
          isEmpty={!hasData}
          emptyText={emptyText}
          value={summary ? formatCurrency(summary.revenue) : undefined}
          changePercent={revenueChange}
          changeLabel="vs previous period"
          sparklineValues={sparklines.revenue}
          detailsHref="/dashboard/analytics"
        />
        <MetricCard
          label="Gross Profit"
          icon="profit"
          accent="leaf"
          isEmpty={!hasData}
          emptyText={emptyText}
          value={summary ? formatCurrency(summary.gross_profit) : undefined}
          changePercent={profitChange}
          changeLabel="vs previous period"
          sparklineValues={sparklines.profit}
          detailsHref="/dashboard/analytics"
        />
        <MetricCard
          label="Profit Margin"
          icon="margin"
          accent="purple"
          isEmpty={!hasData}
          emptyText={emptyText}
          value={summary ? formatPercent(summary.profit_margin) : undefined}
          changePercent={marginChange}
          changeLabel="vs previous period"
          sparklineValues={sparklines.margin}
          detailsHref="/dashboard/analytics"
        />
        <MetricCard
          label="Transactions"
          icon="transactions"
          accent="blue"
          isEmpty={!hasData}
          emptyText={isLoadingSummary ? "Loading…" : summaryError ? "Couldn't load" : "0 recorded"}
          value={summary ? formatNumber(summary.transaction_count) : undefined}
          changePercent={transactionsChange}
          changeLabel="vs previous period"
          detailsHref="/dashboard/transactions"
        />
        <MetricCard
          label="Units Sold"
          icon="products"
          accent="neutral"
          isEmpty={!hasData}
          emptyText={isLoadingSummary ? "Loading…" : summaryError ? "Couldn't load" : "0 sold"}
          value={summary ? formatNumber(summary.units_sold) : undefined}
          detailsHref="/dashboard/products"
        />
      </div>

      {token && (
        <AIBusinessBrief businessId={primaryBusiness.id} token={token} hasData={hasData} />
      )}

      {token && hasData && (
        <div className={styles.chartSection}>
          <RevenueProfitChart
            businessId={primaryBusiness.id}
            dateRange={dateRange}
            token={token}
            title="Revenue Overview"
            transactionCount={summary?.transaction_count}
          />
        </div>
      )}

      {token && (
        <div className={styles.sidePanelsGrid}>
          <AIAssistantPanel businessId={primaryBusiness.id} token={token} />
          <QuickActionsPanel />
        </div>
      )}

      {token && hasData && (
        <div className={styles.bottomPanelsGrid}>
          <TopProductsPanel
            businessId={primaryBusiness.id}
            token={token}
            dateRange={dateRange}
            totalRevenue={summary ? Number(summary.revenue) : 0}
          />
          <RecentTransactionsPanel businessId={primaryBusiness.id} token={token} />
        </div>
      )}

      {summaryError && <p className={styles.error}>{summaryError}</p>}
    </div>
  );
}
