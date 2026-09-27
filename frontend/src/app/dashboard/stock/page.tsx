"use client";

/**
 * Inventory / stock (Step 13, Batch 3): what's on hand per product, a
 * reorder level, and a full history of restocks, damage/loss and
 * corrections. Turning on auto-deduction (Settings > Inventory) makes a
 * sale reduce a matching product's stock automatically.
 *
 * Anyone on the business can read this page. Tracking a product and
 * adjusting its quantity need the "member" role; removing a stock
 * record entirely needs "admin" -- the backend enforces both on every
 * request; hiding the buttons here just avoids showing actions that
 * would fail.
 */
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import StockAdjustmentModal from "@/components/StockAdjustmentModal";
import StockFormModal from "@/components/StockFormModal";
import { ApiError } from "@/lib/api";
import { listBranches } from "@/lib/branches";
import { hasRole } from "@/lib/permissions";
import { deleteStock, fetchStockValue, listStock } from "@/lib/stock";
import type { StockFilters } from "@/lib/stock";
import type { Branch, PaginatedStock, Stock, StockValueSummary } from "@/types";
import styles from "./stock.module.css";

const PAGE_SIZE = 25;

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  minimumFractionDigits: 2,
});

export default function StockPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses, currentUserRole } = useDashboard();
  const canEdit = hasRole(currentUserRole, "member");
  const canDelete = hasRole(currentUserRole, "admin");

  const [searchText, setSearchText] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [branchFilter, setBranchFilter] = useState("");
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const [page, setPage] = useState(1);

  const [data, setData] = useState<PaginatedStock | null>(null);
  const [valueSummary, setValueSummary] = useState<StockValueSummary | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [reloadKey, setReloadKey] = useState(0);
  const [formTarget, setFormTarget] = useState<"new" | Stock | null>(null);
  const [adjustingStock, setAdjustingStock] = useState<Stock | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const businessId = primaryBusiness?.id;

  const buildFilters = useCallback(
    (): StockFilters => ({ branch_id: branchFilter, q: activeQuery, low_stock_only: lowStockOnly }),
    [branchFilter, activeQuery, lowStockOnly]
  );

  useEffect(() => {
    if (!notice || notice.kind === "error") return;
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!token || !businessId) return;
    listBranches(businessId, token)
      .then(setBranches)
      .catch(() => setBranches([]));
  }, [businessId, token]);

  useEffect(() => {
    if (!token || !businessId) return;
    fetchStockValue(businessId, token, branchFilter || undefined)
      .then(setValueSummary)
      .catch(() => setValueSummary(null));
  }, [businessId, token, branchFilter, reloadKey]);

  useEffect(() => {
    if (!token || !businessId) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    listStock(businessId, buildFilters(), page, PAGE_SIZE, token)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load stock.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [businessId, token, page, buildFilters, reloadKey]);

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    setActiveQuery(searchText.trim());
    setPage(1);
  };

  const handleSaved = (_saved: Stock, mode: "created" | "updated") => {
    setFormTarget(null);
    setNotice({ kind: "success", text: mode === "created" ? "Now tracking this product." : "Stock settings updated." });
    if (mode === "created") setPage(1);
    setReloadKey((k) => k + 1);
  };

  const handleAdjustmentSaved = () => {
    setNotice({ kind: "success", text: "Stock updated." });
    setReloadKey((k) => k + 1);
  };

  const handleDelete = async (stock: Stock) => {
    if (!token || !businessId) return;
    setDeletingId(stock.id);
    setNotice(null);
    try {
      await deleteStock(businessId, stock.id, token);
      setConfirmingDeleteId(null);
      setNotice({ kind: "success", text: "Stopped tracking this product." });
      if (data && data.items.length === 1 && page > 1) setPage(page - 1);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setNotice({ kind: "error", text: err instanceof ApiError ? err.message : "Could not remove this stock record." });
    } finally {
      setDeletingId(null);
    }
  };

  if (isLoadingBusinesses) return <p className={styles.muted}>Loading…</p>;

  if (!primaryBusiness || !businessId) {
    return (
      <div>
        <h1 className={styles.title}>Stock</h1>
        <p className={styles.muted}>Create a business on the Overview page before tracking inventory.</p>
      </div>
    );
  }

  const branchNames = new Map(branches.map((b) => [b.id, b.name]));
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const hasFilters = Boolean(branchFilter || activeQuery || lowStockOnly);

  return (
    <div className={styles.page}>
      <div className={styles.headerRow}>
        <div>
          <h1 className={styles.title}>Stock</h1>
          <p className={styles.subtitle}>
            What&apos;s on hand, and a reorder level to get alerted before you run out. Turn on automatic
            deduction on the Settings page to have sales keep this up to date on their own.
          </p>
        </div>
        {canEdit && (
          <button type="button" className={styles.addButton} onClick={() => setFormTarget("new")}>
            + Track a product
          </button>
        )}
      </div>

      {currentUserRole !== null && !canEdit && (
        <p className={styles.muted}>Your role can view stock but not add or change it.</p>
      )}

      {valueSummary && Number(valueSummary.total_value) > 0 && (
        <div className={styles.valueCard}>
          <div>
            <div className={styles.valueLabel}>Stock value</div>
            <div className={styles.valueAmount}>{currencyFormatter.format(Number(valueSummary.total_value))}</div>
          </div>
          {valueSummary.unvalued_count > 0 && (
            <p className={styles.valueHint}>
              {valueSummary.unvalued_count} product{valueSummary.unvalued_count === 1 ? "" : "s"} without a cost set
              {" "}aren&apos;t included — add one on the Edit form to value them too.
            </p>
          )}
        </div>
      )}

      <div className={styles.filters}>
        {data && data.low_stock_count > 0 && (
          <button
            type="button"
            className={`${styles.chip} ${lowStockOnly ? styles.chipActive : ""}`}
            onClick={() => {
              setLowStockOnly((v) => !v);
              setPage(1);
            }}
            aria-pressed={lowStockOnly}
          >
            {lowStockOnly ? "Showing low stock only" : `${data.low_stock_count} low on stock`}
          </button>
        )}
        {branches.length > 0 && (
          <select
            value={branchFilter}
            onChange={(e) => {
              setBranchFilter(e.target.value);
              setPage(1);
            }}
            className={styles.control}
            aria-label="Branch"
          >
            <option value="">All branches</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        )}
        <form onSubmit={handleSearch} className={styles.searchForm}>
          <input
            type="search"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Search product…"
            className={`${styles.control} ${styles.searchInput}`}
            aria-label="Search stock"
          />
          <button type="submit" className={styles.secondaryButton}>
            Search
          </button>
          {activeQuery && (
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => {
                setSearchText("");
                setActiveQuery("");
                setPage(1);
              }}
            >
              Clear
            </button>
          )}
        </form>
      </div>

      {notice && (
        <p className={notice.kind === "error" ? styles.errorText : styles.successText} role={notice.kind === "error" ? "alert" : "status"}>
          {notice.text}
        </p>
      )}
      {error && (
        <p className={styles.errorText} role="alert">
          {error}
        </p>
      )}

      {formTarget !== null && (
        <StockFormModal
          businessId={businessId}
          stock={formTarget === "new" ? null : formTarget}
          branches={branches}
          onClose={() => setFormTarget(null)}
          onSaved={handleSaved}
        />
      )}
      {adjustingStock && (
        <StockAdjustmentModal
          businessId={businessId}
          stock={adjustingStock}
          onClose={() => setAdjustingStock(null)}
          onSaved={handleAdjustmentSaved}
        />
      )}

      {data && data.total === 0 && !isLoading ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>{hasFilters ? "No stock matches these filters" : "Nothing tracked yet"}</p>
          <p className={styles.emptyBody}>
            {canEdit
              ? "Track a product to record how much you have and get alerted when it's running low."
              : "Nothing has been recorded yet."}
          </p>
          {canEdit && (
            <button type="button" className={styles.addButton} onClick={() => setFormTarget("new")}>
              + Track a product
            </button>
          )}
        </div>
      ) : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Product</th>
                  {branches.length > 0 && <th>Branch</th>}
                  <th className={styles.numeric}>On hand</th>
                  <th className={styles.numeric}>Reorder level</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {!data
                  ? Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i}>
                        <td colSpan={5 + (branches.length > 0 ? 1 : 0)}>
                          <span className={styles.skeleton} />
                        </td>
                      </tr>
                    ))
                  : data.items.map((stock) => (
                      <tr key={stock.id}>
                        <td className={styles.productCell}>{stock.product}</td>
                        {branches.length > 0 && (
                          <td>{stock.branch_id ? (branchNames.get(stock.branch_id) ?? "—") : "Shared"}</td>
                        )}
                        <td className={styles.numeric}>{Number(stock.quantity_on_hand)}</td>
                        <td className={styles.numeric}>
                          {Number(stock.reorder_level) > 0 ? Number(stock.reorder_level) : "—"}
                        </td>
                        <td>
                          {stock.is_low ? (
                            <span className={styles.lowBadge}>Low</span>
                          ) : (
                            <span className={styles.okBadge}>OK</span>
                          )}
                        </td>
                        <td>
                          {confirmingDeleteId === stock.id ? (
                            <div className={styles.rowActions}>
                              <button
                                type="button"
                                className={styles.confirmDeleteButton}
                                onClick={() => handleDelete(stock)}
                                disabled={deletingId === stock.id}
                              >
                                {deletingId === stock.id ? "Removing…" : "Confirm"}
                              </button>
                              <button
                                type="button"
                                className={styles.rowButton}
                                onClick={() => setConfirmingDeleteId(null)}
                                disabled={deletingId === stock.id}
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div className={styles.rowActions}>
                              {canEdit && (
                                <button type="button" className={styles.rowButton} onClick={() => setAdjustingStock(stock)}>
                                  Adjust
                                </button>
                              )}
                              {canEdit && (
                                <button
                                  type="button"
                                  className={styles.rowButton}
                                  onClick={() => {
                                    setConfirmingDeleteId(null);
                                    setFormTarget(stock);
                                  }}
                                >
                                  Edit
                                </button>
                              )}
                              {canDelete && (
                                <button
                                  type="button"
                                  className={styles.rowDeleteButton}
                                  onClick={() => setConfirmingDeleteId(stock.id)}
                                >
                                  Remove
                                </button>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>

          {data && (
            <div className={styles.pagination}>
              <span>
                {data.total} product{data.total === 1 ? "" : "s"} tracked · Page {data.page} of {totalPages}
              </span>
              <div className={styles.pageButtons}>
                <button
                  type="button"
                  className={styles.pageButton}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1 || isLoading}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className={styles.pageButton}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages || isLoading}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
