"use client";

import { useEffect, useState } from "react";
import { fetchAnalyticsProducts } from "@/lib/analytics";
import { ApiError } from "@/lib/api";
import type { DateRangeValue, ProductAnalyticsItem } from "@/types";
import styles from "./TopProductsPanel.module.css";

interface Props {
  businessId: string;
  token: string;
  dateRange: DateRangeValue;
  /** The period's true total revenue (from the Overview page's own
   * summary fetch), so "Share" reflects each product's share of the
   * whole business in this period -- not just a share of the 5 products
   * shown here, which would overstate every row's percentage. */
  totalRevenue: number;
}

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 0,
});

const PRODUCT_COLORS = ["gold", "leaf", "purple", "blue"] as const;

export default function TopProductsPanel({ businessId, token, dateRange, totalRevenue }: Props) {
  const [items, setItems] = useState<ProductAnalyticsItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchAnalyticsProducts(businessId, dateRange, token, 5)
      .then((data) => {
        if (!cancelled) setItems(data.top_selling);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load products.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [businessId, token, dateRange]);

  return (
    <div className={styles.panel}>
      <h2 className={styles.title}>Top Products</h2>

      {isLoading && <p className={styles.muted}>Loading…</p>}
      {!isLoading && error && <p className={styles.muted}>{error}</p>}
      {!isLoading && !error && items.length === 0 && (
        <p className={styles.muted}>No product sales in this period yet.</p>
      )}

      {!isLoading && !error && items.length > 0 && (
        <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>#</th>
              <th>Product</th>
              <th>Revenue</th>
              <th>Share</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => {
              const revenue = Number(item.revenue);
              const share = totalRevenue > 0 ? (revenue / totalRevenue) * 100 : 0;
              const color = PRODUCT_COLORS[i % PRODUCT_COLORS.length];
              return (
                <tr key={item.product}>
                  <td className={styles.rank}>{i + 1}</td>
                  <td>
                    <span className={styles.productCell}>
                      <span className={`${styles.productIcon} ${styles[`icon_${color}`]}`}>
                        {item.product.charAt(0).toUpperCase()}
                      </span>
                      {item.product}
                    </span>
                  </td>
                  <td>{currencyFormatter.format(revenue)}</td>
                  <td>
                    <div className={styles.shareCell}>
                      <div className={styles.shareBar}>
                        <div
                          className={`${styles.shareFill} ${styles[`fill_${color}`]}`}
                          style={{ width: `${Math.min(share, 100).toFixed(1)}%` }}
                        />
                      </div>
                      <span className={styles.sharePercent}>{share.toFixed(0)}%</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}
