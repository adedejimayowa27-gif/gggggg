"use client";

import { useState, FormEvent } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { apiFetch, ApiError } from "@/lib/api";
import type { Business } from "@/types";
import MetricCard from "@/components/MetricCard";
import styles from "./overview.module.css";

export default function OverviewPage() {
  const { token } = useAuth();
  const { businesses, primaryBusiness, isLoadingBusinesses, refreshBusinesses } = useDashboard();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

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

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h1>{primaryBusiness.name}</h1>
          {primaryBusiness.industry && (
            <span className={styles.industryChip}>{primaryBusiness.industry}</span>
          )}
        </div>
        <button className={styles.newBusinessButton} onClick={() => setShowCreateForm((s) => !s)}>
          {showCreateForm ? "Cancel" : "+ New business"}
        </button>
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

      <div className={styles.cardsGrid}>
        <MetricCard label="Revenue" icon="revenue" emptyText="No transactions yet" />
        <MetricCard label="Gross Profit" icon="profit" emptyText="No transactions yet" />
        <MetricCard label="Profit Margin" icon="margin" emptyText="No transactions yet" />
        <MetricCard label="Transactions" icon="transactions" emptyText="0 recorded" />
        <MetricCard label="Products" icon="products" emptyText="0 added" />
      </div>

      {businesses.length > 1 && (
        <p style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: "1.5rem" }}>
          Showing your first business. Switching between businesses is coming soon.
        </p>
      )}
    </div>
  );
}
