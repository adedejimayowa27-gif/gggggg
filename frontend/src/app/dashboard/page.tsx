"use client";

import { useEffect, useState, FormEvent } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { apiFetch, ApiError } from "@/lib/api";
import { fetchAnalyticsSummary } from "@/lib/analytics";
import type { AnalyticsSummary, Business, DateRangeValue } from "@/types";
import MetricCard from "@/components/MetricCard";
import DateRangePicker from "@/components/DateRangePicker";
import AlertsPanel from "@/components/AlertsPanel";
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

export default function OverviewPage() {
  const { token } = useAuth();
  const { businesses, primaryBusiness, isLoadingBusinesses, refreshBusinesses } = useDashboard();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const [dateRange, setDateRange] = useState<DateRangeValue>({ range: "30d" });
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !primaryBusiness) return;

    let cancelled = false;
    setIsLoadingSummary(true);
    setSummaryError(null);

    fetchAnalyticsSummary(primaryBusiness.id, dateRange, token)
      .then((data) => {
        if (!cancelled) setSummary(data);
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
      await apiFetch<Business>("/businesses", {
        method: "POST",
        authToken: token,
        body: JSON.stringify({ name, industry: industry || undefined }),
      });
      setName("");
      setIndustry("");
      setShowCreateForm(false);
      await refreshBusinesses();
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

      <div className={styles.uploadSection}>
        <div className={styles.uploadText}>
          <h2>No transaction data yet</h2>
          <p>
            Upload your sales, expenses, or bank transactions to unlock real metrics,
            forecasting, and AI insights.
          </p>
        </div>
        <Link href="/dashboard/transactions" className={styles.uploadButton}>
          Upload Transactions
        </Link>
      </div>

      {token && <AlertsPanel businessId={primaryBusiness.id} token={token} compact />}

      <div className={styles.cardsGrid}>
        <MetricCard
          label="Revenue"
          icon="revenue"
          isEmpty={!hasData}
          emptyText={emptyText}
          value={summary ? formatCurrency(summary.revenue) : undefined}
        />
        <MetricCard
          label="Gross Profit"
          icon="profit"
          isEmpty={!hasData}
          emptyText={emptyText}
          value={summary ? formatCurrency(summary.gross_profit) : undefined}
        />
        <MetricCard
          label="Profit Margin"
          icon="margin"
          isEmpty={!hasData}
          emptyText={emptyText}
          value={summary ? formatPercent(summary.profit_margin) : undefined}
        />
        <MetricCard
          label="Transactions"
          icon="transactions"
          isEmpty={!hasData}
          emptyText={isLoadingSummary ? "Loading…" : summaryError ? "Couldn't load" : "0 recorded"}
          value={summary ? formatNumber(summary.transaction_count) : undefined}
        />
        <MetricCard
          label="Units Sold"
          icon="products"
          isEmpty={!hasData}
          emptyText={isLoadingSummary ? "Loading…" : summaryError ? "Couldn't load" : "0 sold"}
          value={summary ? formatNumber(summary.units_sold) : undefined}
        />
      </div>

      {summaryError && <p className={styles.error}>{summaryError}</p>}

      {businesses.length > 1 && (
        <p style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: "1.5rem" }}>
          Showing your first business. Switching between businesses is coming soon.
        </p>
      )}
    </div>
  );
}
