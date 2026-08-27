"use client";

/**
 * Product ranking card.
 *
 * Renders one of the four ranked lists from GET .../analytics/products
 * (top-selling, highest-profit, lowest-profit, slow-moving). All four
 * share the same shape -- a ranked list of ProductAnalyticsItem -- so
 * one component handles all of them, parameterized by which field to
 * feature as the headline metric.
 */
import type { ProductAnalyticsItem } from "@/types";
import styles from "./ProductRankingCard.module.css";

type PrimaryMetric = "units_sold" | "gross_profit";

interface Props {
  title: string;
  description: string;
  items: ProductAnalyticsItem[];
  primaryMetric: PrimaryMetric;
  isLoading?: boolean;
  error?: string | null;
}

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

function formatNumber(value: string): string {
  return numberFormatter.format(Number(value));
}

function primaryValue(item: ProductAnalyticsItem, metric: PrimaryMetric): string {
  return metric === "units_sold" ? formatNumber(item.units_sold) : formatCurrency(item.gross_profit);
}

function primaryLabel(metric: PrimaryMetric): string {
  return metric === "units_sold" ? "units" : "profit";
}

export default function ProductRankingCard({
  title,
  description,
  items,
  primaryMetric,
  isLoading = false,
  error = null,
}: Props) {
  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{title}</h2>
        <p className={styles.description}>{description}</p>
      </div>

      {isLoading ? (
        <div className={styles.placeholder}>Loading…</div>
      ) : error ? (
        <div className={styles.placeholder}>{error}</div>
      ) : items.length === 0 ? (
        <div className={styles.placeholder}>No products in this range yet</div>
      ) : (
        <ol className={styles.list}>
          {items.map((item, index) => {
            const profitIsNegative = Number(item.gross_profit) < 0;
            return (
              <li key={item.product} className={styles.row}>
                <span className={styles.rank}>{index + 1}</span>
                <div className={styles.rowMain}>
                  <span className={styles.productName}>{item.product}</span>
                  <span className={styles.rowSub}>
                    {formatNumber(item.units_sold)} sold · {formatCurrency(item.revenue)} revenue
                  </span>
                </div>
                <div className={styles.rowMetric}>
                  <span
                    className={`${styles.metricValue} ${
                      primaryMetric === "gross_profit" && profitIsNegative ? styles.metricNegative : ""
                    }`}
                  >
                    {primaryValue(item, primaryMetric)}
                  </span>
                  <span className={styles.metricLabel}>{primaryLabel(primaryMetric)}</span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
