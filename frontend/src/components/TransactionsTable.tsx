"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiFetch, apiFetchBlob, ApiError } from "@/lib/api";
import { listBranches } from "@/lib/branches";
import { deleteTransaction } from "@/lib/transactions";
import type { Branch, PaginatedTransactions, Transaction } from "@/types";
import TransactionFormModal from "@/components/TransactionFormModal";
import styles from "./TransactionsTable.module.css";

interface Props {
  businessId: string;
  refreshSignal?: number;
  /** Pre-fills the search box -- set from the URL's ?q= param, so
   * arriving here via the topbar search (which navigates to
   * /dashboard/transactions?q=...) actually shows filtered results
   * instead of silently discarding what was typed. */
  initialQuery?: string;
  /** "member"+ may add and correct transactions. The backend enforces this
   * on every request; hiding the buttons is only so people aren't shown
   * actions that would just fail. */
  canEdit?: boolean;
  /** "admin"+ may delete a transaction. */
  canDelete?: boolean;
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

function SkeletonRows({ columns }: { columns: number }) {
  return (
    <>
      {Array.from({ length: 8 }).map((_, i) => (
        <tr key={i}>
          {Array.from({ length: columns }).map((_, j) => (
            <td key={j}>
              <span className={styles.skeletonCell} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export default function TransactionsTable({
  businessId,
  refreshSignal,
  initialQuery,
  canEdit = false,
  canDelete = false,
}: Props) {
  const { token } = useAuth();
  const [data, setData] = useState<PaginatedTransactions | null>(null);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [searchInput, setSearchInput] = useState(initialQuery ?? "");
  const [activeQuery, setActiveQuery] = useState(initialQuery ?? "");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [branchFilter, setBranchFilter] = useState("");

  // Manual entry / editing / deleting (Step 13, Batch 1). `reloadKey` refetches
  // the current page in place -- unlike refreshSignal, which is for imports
  // and deliberately jumps back to page 1.
  const [reloadKey, setReloadKey] = useState(0);
  const [formTarget, setFormTarget] = useState<"new" | Transaction | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (!notice || notice.kind === "error") return;
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!token) return;
    // Fetched once, not tied to any filter state -- the branch list
    // itself doesn't change based on what's currently filtered.
    listBranches(businessId, token)
      .then(setBranches)
      .catch(() => setBranches([]));
  }, [businessId, token]);

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    const queryParam = activeQuery ? `&q=${encodeURIComponent(activeQuery)}` : "";
    const branchParam = branchFilter ? `&branch_id=${branchFilter}` : "";
    apiFetch<PaginatedTransactions>(
      `/businesses/${businessId}/transactions?page=${page}&page_size=${PAGE_SIZE}${queryParam}${branchParam}`,
      { authToken: token }
    )
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setIsLoading(false));
  }, [businessId, token, page, refreshSignal, activeQuery, branchFilter, reloadKey]);

  // Refreshing after a new import should show the latest data, not
  // whatever page the user happened to be on before.
  useEffect(() => {
    setPage(1);
  }, [refreshSignal]);

  const handleBranchFilterChange = (value: string) => {
    setPage(1);
    setBranchFilter(value);
  };

  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExport = async () => {
    if (!token) return;
    setIsExporting(true);
    setExportError(null);
    try {
      const params = new URLSearchParams();
      if (activeQuery) params.set("q", activeQuery);
      if (branchFilter) params.set("branch_id", branchFilter);
      const blob = await apiFetchBlob(
        `/businesses/${businessId}/transactions/export?${params.toString()}`,
        { authToken: token }
      );
      // The backend sets a real filename via Content-Disposition, but
      // that header isn't reachable from a Blob -- the browser applies
      // it automatically for a same-origin navigation, but this is a
      // fetch()'d blob turned into a synthetic download, so the `a`
      // tag's own `download` attribute is what actually names the file
      // here. Close enough (a fixed name rather than the server's exact
      // one) and simpler than re-parsing the response headers for it.
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "transactions.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : "Could not export transactions.");
    } finally {
      setIsExporting(false);
    }
  };

  const handleSaved = (_saved: Transaction, mode: "created" | "updated") => {
    setFormTarget(null);
    setNotice({ kind: "success", text: mode === "created" ? "Sale added." : "Sale updated." });
    if (mode === "created") setPage(1);
    setReloadKey((k) => k + 1);
  };

  const handleDelete = async (transaction: Transaction) => {
    if (!token) return;
    setDeletingId(transaction.id);
    setNotice(null);
    try {
      await deleteTransaction(businessId, transaction.id, token);
      setConfirmingDeleteId(null);
      setNotice({ kind: "success", text: "Sale deleted." });
      // Deleting the only row on the last page would otherwise leave an empty page.
      if (data && data.items.length === 1 && page > 1) setPage(page - 1);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setNotice({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Could not delete this sale.",
      });
    } finally {
      setDeletingId(null);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setActiveQuery(searchInput.trim());
  };

  const handleClearSearch = () => {
    setSearchInput("");
    setActiveQuery("");
    setPage(1);
  };

  // Defined once and reused in both the empty-state and normal render
  // paths below, rather than duplicating this markup -- the branch
  // dropdown only appears at all when the business actually has
  // branches, so a business that's never touched that feature sees no
  // change here.
  const filterBar = (
    <>
      <form className={styles.searchRow} onSubmit={handleSearchSubmit}>
        <input
          type="search"
          placeholder="Search by product, category, customer, payment method…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className={styles.searchInput}
        />
        {branches.length > 0 && (
          <select
            value={branchFilter}
            onChange={(e) => handleBranchFilterChange(e.target.value)}
            className={styles.branchSelect}
          >
            <option value="">All branches</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        )}
        {activeQuery && (
          <button type="button" className={styles.clearButton} onClick={handleClearSearch}>
            Clear
          </button>
        )}
        <div className={styles.actionButtons}>
          {canEdit && (
            <button type="button" className={styles.addButton} onClick={() => setFormTarget("new")}>
              + Add sale
            </button>
          )}
          <button
            type="button"
            className={styles.exportButton}
            onClick={handleExport}
            disabled={isExporting}
          >
            {isExporting ? "Exporting…" : "Export CSV"}
          </button>
        </div>
      </form>
      {exportError && <p className={styles.exportError}>{exportError}</p>}
      {notice && (
        <p
          className={notice.kind === "error" ? styles.exportError : styles.successNotice}
          role={notice.kind === "error" ? "alert" : "status"}
        >
          {notice.text}
        </p>
      )}
    </>
  );

  const formModal =
    formTarget !== null ? (
      <TransactionFormModal
        businessId={businessId}
        transaction={formTarget === "new" ? null : formTarget}
        branches={branches}
        onClose={() => setFormTarget(null)}
        onSaved={handleSaved}
      />
    ) : null;

  if (!isLoading && (!data || data.total === 0)) {
    return (
      <div>
        {filterBar}
        {formModal}
        <div className={styles.empty}>
          {activeQuery ? (
            <>
              <p className={styles.emptyTitle}>No matches for &ldquo;{activeQuery}&rdquo;</p>
              <p className={styles.emptyBody}>Try a different product, category, customer, or payment method.</p>
            </>
          ) : (
            <>
              <p className={styles.emptyTitle}>No transactions yet</p>
              <p className={styles.emptyBody}>
                {canEdit
                  ? "Upload a file above, or add your first sale by hand."
                  : "Upload a file above to see your sales history here."}
              </p>
            </>
          )}
        </div>
      </div>
    );
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className={styles.wrap}>
      {filterBar}
      {formModal}
      {activeQuery && data && (
        <p className={styles.resultCount}>
          {data.total} {data.total === 1 ? "result" : "results"} for &ldquo;{activeQuery}&rdquo;
        </p>
      )}
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
              {canEdit && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {isLoading || !data ? (
              <SkeletonRows columns={canEdit ? 9 : 8} />
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
                  {canEdit && (
                    <td>
                      {confirmingDeleteId === t.id ? (
                        <div className={styles.rowActions}>
                          <button
                            type="button"
                            className={styles.confirmDeleteButton}
                            onClick={() => handleDelete(t)}
                            disabled={deletingId === t.id}
                          >
                            {deletingId === t.id ? "Deleting…" : "Confirm delete"}
                          </button>
                          <button
                            type="button"
                            className={styles.rowButton}
                            onClick={() => setConfirmingDeleteId(null)}
                            disabled={deletingId === t.id}
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className={styles.rowActions}>
                          <button
                            type="button"
                            className={styles.rowButton}
                            onClick={() => {
                              setConfirmingDeleteId(null);
                              setFormTarget(t);
                            }}
                          >
                            Edit
                          </button>
                          {canDelete && (
                            <button
                              type="button"
                              className={styles.rowDeleteButton}
                              onClick={() => setConfirmingDeleteId(t.id)}
                            >
                              Delete
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                  )}
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
