"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiFetch } from "@/lib/api";
import type { PaginatedTransactions } from "@/types";
import styles from "./TransactionsTable.module.css";

interface Props {
  businessId: string;
  refreshSignal?: number;
}

const PAGE_SIZE = 25;

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  minimumFractionDigits: 2,
});

const dateFormatter = new Intl.DateTimeFormat("en-NG", {
  day: "numeric",
  month: "short",
  year: "numeric",
  // Pinned to UTC deliberately, matching how the date is constructed
  // below -- without this, the formatter converts the UTC instant back
  // to the viewer's *local* timezone before extracting the calendar
  // date, which for anyone west of UTC can still shift the displayed
  // date back a day even though the Date object itself was built
  // correctly. Both halves (construction AND formatting) have to agree
  // on UTC, or the bug just moves from one step to the other.
  timeZone: "UTC",
});

function formatCurrency(value: string): string {
  return currencyFormatter.format(Number(value));
}

function formatDate(value: string): string {
  // Transaction.date arrives as a plain "YYYY-MM-DD" -- parsed as UTC
  // explicitly so it never shifts a day depending on the viewer's local
  // timezone offset (a bare `new Date("2026-01-15")` is parsed as UTC
  // midnight by spec, but formatting it with a local-timezone formatter
  // can then display as the 14th for anyone west of UTC).
  const [year, month, day] = value.split("-").map(Number);
  return dateFormatter.format(new Date(Date.UTC(year, month - 1, day)));
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 8 }).map((_, i) => (
        <tr key={i}>
          {Array.from({ length: 8 }).map((_, j) => (
            <td key={j}>
              <span className={styles.skeletonCell} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export default function TransactionsTable({ businessId, refreshSignal }: Props) {
  const { token } = useAuth();
  const [data, setData] = useState<PaginatedTransactions | null>(null);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    apiFetch<PaginatedTransactions>(
      `/businesses/${businessId}/transactions?page=${page}&page_size=${PAGE_SIZE}`,
      { authToken: token }
    )
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setIsLoading(false));
  }, [businessId, token, page, refreshSignal]);

  // Refreshing after a new import should show the latest data, not
  // whatever page the user happened to be on before.
  useEffect(() => {
    setPage(1);
  }, [refreshSignal]);

  if (!isLoading && (!data || data.total === 0)) {
    return (
      <div className={styles.empty}>
        <p className={styles.emptyTitle}>No transactions yet</p>
        <p className={styles.emptyBody}>Upload a file above to see your sales history here.</p>
      </div>
    );
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className={styles.wrap}>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Date</th>
              <th>Product</th>
              <th>Quantity</th>
              <th>Selling Price</th>
              <th>Cost Price</th>
              <th>Category</th>
              <th>Customer</th>
              <th>Payment Method</th>
            </tr>
          </thead>
          <tbody>
            {isLoading || !data ? (
              <SkeletonRows />
            ) : (
              data.items.map((t) => (
                <tr key={t.id}>
                  <td>{formatDate(t.date)}</td>
                  <td className={styles.productCell}>{t.product}</td>
                  <td>{t.quantity}</td>
                  <td>{formatCurrency(t.selling_price)}</td>
                  <td>{t.cost_price ? formatCurrency(t.cost_price) : "—"}</td>
                  <td>{t.category ?? "—"}</td>
                  <td>{t.customer ?? "—"}</td>
                  <td>{t.payment_method ?? "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {data && (
        <div className={styles.pagination}>
          <span>
            {data.total} total transaction{data.total === 1 ? "" : "s"} · Page {data.page} of{" "}
            {totalPages}
          </span>
          <div className={styles.pageButtons}>
            <button
              className={styles.pageButton}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || isLoading}
            >
              Previous
            </button>
            <button
              className={styles.pageButton}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || isLoading}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
