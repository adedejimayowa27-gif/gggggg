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

  if (isLoading && !data) {
    return <p style={{ color: "var(--muted)" }}>Loading transactions…</p>;
  }

  if (!data || data.total === 0) {
    return <div className={styles.empty}>No transactions yet. Upload a file above to get started.</div>;
  }

  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));

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
            </tr>
          </thead>
          <tbody>
            {data.items.map((t) => (
              <tr key={t.id}>
                <td>{t.date}</td>
                <td>{t.product}</td>
                <td>{t.quantity}</td>
                <td>{t.selling_price}</td>
                <td>{t.cost_price ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.pagination}>
        <span>
          {data.total} total transaction{data.total === 1 ? "" : "s"} · Page {data.page} of{" "}
          {totalPages}
        </span>
        <div className={styles.pageButtons}>
          <button
            className={styles.pageButton}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
          >
            Previous
          </button>
          <button
            className={styles.pageButton}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
