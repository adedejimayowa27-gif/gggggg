"use client";

/**
 * Status column note: the brief this was designed against asked for
 * Completed/Pending/Failed status indicators. This app's Transaction
 * model has no status field at all, and genuinely can't -- every
 * transaction here is a historical sales record imported from a
 * spreadsheet or synced sheet, not a live payment being processed.
 * There's no "pending" or "failed" state a past sale could be in; a row
 * that failed validation during import never became a Transaction in
 * the first place (see the import pipeline's row-error handling), and
 * one that succeeded is, definitionally, a completed record. Rather
 * than invent three fake states with no real backing data (which would
 * actively mislead -- implying payment-processing tracking that doesn't
 * exist), every row shows a single honest "Recorded" badge.
 */
import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { PaginatedTransactions } from "@/types";
import styles from "./RecentTransactionsPanel.module.css";

interface Props {
  businessId: string;
  token: string;
}

const dateFormatter = new Intl.DateTimeFormat("en-NG", { day: "numeric", month: "short" });
const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 0,
});

export default function RecentTransactionsPanel({ businessId, token }: Props) {
  const [transactions, setTransactions] = useState<PaginatedTransactions | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    apiFetch<PaginatedTransactions>(`/businesses/${businessId}/transactions?page=1&page_size=6`, {
      authToken: token,
    })
      .then((data) => {
        if (!cancelled) setTransactions(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load transactions.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [businessId, token]);

  const items = transactions?.items ?? [];

  return (
    <div className={styles.panel}>
      <h2 className={styles.title}>Recent Transactions</h2>

      {isLoading && <p className={styles.muted}>Loading…</p>}
      {!isLoading && error && <p className={styles.muted}>{error}</p>}
      {!isLoading && !error && items.length === 0 && (
        <p className={styles.muted}>No transactions recorded yet.</p>
      )}

      {!isLoading && !error && items.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Date</th>
              <th>Product</th>
              <th>Amount</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((txn) => (
              <tr key={txn.id}>
                <td className={styles.muted}>{dateFormatter.format(new Date(txn.date))}</td>
                <td className={styles.productName}>{txn.product}</td>
                <td>{currencyFormatter.format(Number(txn.quantity) * Number(txn.selling_price))}</td>
                <td>
                  <span className={styles.statusBadge}>Recorded</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
