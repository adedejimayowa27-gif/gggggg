"use client";

/**
 * New vs. returning customers.
 *
 * The retention metric every standard customer-analysis report leads
 * with, and one this app didn't compute anywhere before this batch --
 * checked against both the frontend and app.services.ai_tools (what
 * the AI assistant itself can answer) before building this, since
 * there'd be no point duplicating something that already existed.
 *
 * Backed by GET .../analytics/customer-loyalty (new endpoint): a
 * customer counts as "returning" if their first-ever transaction with
 * the business predates the selected period's start -- not just
 * "appears more than once in this period" -- so a single busy new
 * customer with two visits this week is still correctly "new," and
 * someone who bought once last year and again today is "returning"
 * even though this period alone would only show one visit.
 */
import { useEffect, useState } from "react";
import { fetchCustomerLoyalty } from "@/lib/analytics";
import { ApiError } from "@/lib/api";
import type { CustomerLoyalty, DateRangeValue } from "@/types";
import styles from "./CustomerLoyaltyPanel.module.css";

interface Props {
  businessId: string;
  dateRange: DateRangeValue;
  token: string;
}

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 0,
});

const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export default function CustomerLoyaltyPanel({ businessId, dateRange, token }: Props) {
  const [data, setData] = useState<CustomerLoyalty | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchCustomerLoyalty(businessId, dateRange, token)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setData(null);
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

  const newRevenue = data ? Number(data.new.revenue) : 0;
  const returningRevenue = data ? Number(data.returning.revenue) : 0;
  const totalRevenue = newRevenue + returningRevenue;
  const returningSharePct = totalRevenue > 0 ? (returningRevenue / totalRevenue) * 100 : 0;
  const newSharePct = totalRevenue > 0 ? 100 - returningSharePct : 0;

  const avgPerCustomer = (revenue: number, count: number) => (count > 0 ? revenue / count : 0);

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.iconWrap}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="1.6" />
            <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            <circle cx="17" cy="7" r="2.4" stroke="currentColor" strokeWidth="1.4" />
            <path d="M15.5 13.2c2.6.4 4.5 2.6 4.5 5.3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
        </div>
        <div>
          <h2 className={styles.title}>Customer loyalty</h2>
          <p className={styles.description}>New vs. returning customers this period</p>
        </div>
      </div>

      {isLoading ? (
        <div className={styles.placeholder}>Loading…</div>
      ) : error ? (
        <div className={styles.placeholder}>{error}</div>
      ) : !data || !data.has_data ? (
        <div className={styles.placeholder}>
          None of your transactions have a customer recorded yet, so returning customers can&rsquo;t be
          identified.
        </div>
      ) : totalRevenue === 0 ? (
        <div className={styles.placeholder}>No revenue from identified customers in this range yet</div>
      ) : (
        <>
          <p className={styles.headline}>
            <strong>{Math.round(returningSharePct)}%</strong> of revenue in this range came from{" "}
            <strong>returning</strong> customers.
          </p>

          <div className={styles.splitBar}>
            <div className={styles.splitNew} style={{ width: `${newSharePct}%` }} />
            <div className={styles.splitReturning} style={{ width: `${returningSharePct}%` }} />
          </div>

          <div className={styles.segments}>
            <div className={styles.segment}>
              <div className={styles.segmentHead}>
                <span className={`${styles.dot} ${styles.dotNew}`} />
                <span className={styles.segmentLabel}>New customers</span>
              </div>
              <div className={styles.segmentValue}>{currencyFormatter.format(newRevenue)}</div>
              <div className={styles.segmentSub}>
                {numberFormatter.format(data.new.customer_count)}{" "}
                {data.new.customer_count === 1 ? "customer" : "customers"} ·{" "}
                {currencyFormatter.format(avgPerCustomer(newRevenue, data.new.customer_count))} avg
              </div>
            </div>
            <div className={styles.segment}>
              <div className={styles.segmentHead}>
                <span className={`${styles.dot} ${styles.dotReturning}`} />
                <span className={styles.segmentLabel}>Returning customers</span>
              </div>
              <div className={styles.segmentValue}>{currencyFormatter.format(returningRevenue)}</div>
              <div className={styles.segmentSub}>
                {numberFormatter.format(data.returning.customer_count)}{" "}
                {data.returning.customer_count === 1 ? "customer" : "customers"} ·{" "}
                {currencyFormatter.format(avgPerCustomer(returningRevenue, data.returning.customer_count))} avg
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
