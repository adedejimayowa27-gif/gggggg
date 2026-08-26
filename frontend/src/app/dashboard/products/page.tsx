"use client";

/**
 * Products page.
 *
 * Renders the four ranked product lists from GET .../analytics/products
 * (top-selling, highest-profit, lowest-profit, slow-moving) behind the
 * same page-level DateRangePicker pattern used by Overview and Analytics.
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { fetchAnalyticsProducts } from "@/lib/analytics";
import { ApiError } from "@/lib/api";
import type { DateRangeValue, ProductAnalytics } from "@/types";
import DateRangePicker from "@/components/DateRangePicker";
import ProductRankingCard from "@/components/ProductRankingCard";
import ComingSoon from "@/components/ComingSoon";
import styles from "./products.module.css";

export default function ProductsPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();
  const [dateRange, setDateRange] = useState<DateRangeValue>({ range: "30d" });
  const [data, setData] = useState<ProductAnalytics | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !primaryBusiness) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchAnalyticsProducts(primaryBusiness.id, dateRange, token)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setData(null);
          setError(err instanceof ApiError ? err.message : "Could not load product analytics.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
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
        title="Products"
        description="Create a business to start seeing product performance here."
      />
    );
  }

  return (
    <div>
      <div className={styles.header}>
        <h1>Products</h1>
        <DateRangePicker value={dateRange} onChange={setDateRange} />
      </div>

      <div className={styles.grid}>
        <ProductRankingCard
          title="Top-Selling"
          description="Most units sold in this range"
          items={data?.top_selling ?? []}
          primaryMetric="units_sold"
          isLoading={isLoading}
          error={error}
        />
        <ProductRankingCard
          title="Highest-Profit"
          description="Most gross profit generated in this range"
          items={data?.highest_profit ?? []}
          primaryMetric="gross_profit"
          isLoading={isLoading}
          error={error}
        />
        <ProductRankingCard
          title="Lowest-Profit"
          description="Least gross profit generated in this range"
          items={data?.lowest_profit ?? []}
          primaryMetric="gross_profit"
          isLoading={isLoading}
          error={error}
        />
        <ProductRankingCard
          title="Slow-Moving"
          description="Fewest units sold in this range"
          items={data?.slow_moving ?? []}
          primaryMetric="units_sold"
          isLoading={isLoading}
          error={error}
        />
      </div>
    </div>
  );
}
