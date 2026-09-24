"use client";

/**
 * Operating expenses (Step 13, Batch 2): rent, salaries, transport and the
 * other running costs that come off gross profit to give net profit.
 *
 * Anyone on the business can read this page. Adding and correcting an
 * expense needs the "member" role, deleting one needs "admin" -- the
 * backend enforces both on every request; hiding the buttons here just
 * avoids showing actions that would fail.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import ExpenseFormModal from "@/components/ExpenseFormModal";
import { ApiError } from "@/lib/api";
import { listBranches } from "@/lib/branches";
import {
  deleteExpense,
  fetchExpenseCategories,
  fetchExpenseSummary,
  listExpenses,
} from "@/lib/expenses";
import type { ExpenseFilters } from "@/lib/expenses";
import { hasRole } from "@/lib/permissions";
import type { Branch, Expense, ExpenseSummary, PaginatedExpenses } from "@/types";
import styles from "./expenses.module.css";

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
  timeZone: "UTC",
});

function formatDate(value: string): string {
  // "YYYY-MM-DD" parsed as UTC and formatted as UTC so it never shifts a day.
  const [year, month, day] = value.split("-").map(Number);
  return dateFormatter.format(new Date(Date.UTC(year, month - 1, day)));
}

function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

type Preset = "this-month" | "last-month" | "last-30" | "all" | "custom";

/** [start, end] for a preset, in the person's own timezone. "" = no bound. */
function presetRange(preset: Exclude<Preset, "custom">): [string, string] {
  const now = new Date();
  if (preset === "this-month") return [isoDate(new Date(now.getFullYear(), now.getMonth(), 1)), ""];
  if (preset === "last-month") {
    return [
      isoDate(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
      isoDate(new Date(now.getFullYear(), now.getMonth(), 0)),
    ];
  }
  if (preset === "last-30") {
    const start = new Date(now);
    start.setDate(start.getDate() - 29);
    return [isoDate(start), ""];
  }
  return ["", ""];
}

const PRESET_LABELS: { key: Exclude<Preset, "custom">; label: string }[] = [
  { key: "this-month", label: "This month" },
  { key: "last-month", label: "Last month" },
  { key: "last-30", label: "Last 30 days" },
  { key: "all", label: "All time" },
];

export default function ExpensesPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses, currentUserRole } = useDashboard();
  const canEdit = hasRole(currentUserRole, "member");
  const canDelete = hasRole(currentUserRole, "admin");

  const [preset, setPreset] = useState<Preset>("this-month");
  const [startDate, setStartDate] = useState(() => presetRange("this-month")[0]);
  const [endDate, setEndDate] = useState(() => presetRange("this-month")[1]);
  const [category, setCategory] = useState("");
  const [branchFilter, setBranchFilter] = useState("");
  const [searchText, setSearchText] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [page, setPage] = useState(1);

  const [data, setData] = useState<PaginatedExpenses | null>(null);
  const [summary, setSummary] = useState<ExpenseSummary | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [reloadKey, setReloadKey] = useState(0);
  const [formTarget, setFormTarget] = useState<"new" | Expense | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const businessId = primaryBusiness?.id;

  const buildFilters = useCallback(
    (): ExpenseFilters => ({
      start_date: startDate,
      end_date: endDate,
      category,
      q: activeQuery,
      branch_id: branchFilter,
    }),
    [startDate, endDate, category, activeQuery, branchFilter]
  );

  useEffect(() => {
    if (!notice || notice.kind === "error") return;
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  // Branches: loaded once per business.
  useEffect(() => {
    if (!token || !businessId) return;
    listBranches(businessId, token)
      .then(setBranches)
      .catch(() => setBranches([]));
  }, [businessId, token]);

  // Category suggestions: refreshed after every change, since a save can
  // introduce a new category.
  useEffect(() => {
    if (!token || !businessId) return;
    fetchExpenseCategories(businessId, token)
      .then(setCategories)
      .catch(() => setCategories([]));
  }, [businessId, token, reloadKey]);

  // The list: refetched on any filter, page or data change.
  useEffect(() => {
    if (!token || !businessId) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    listExpenses(businessId, buildFilters(), page, PAGE_SIZE, token)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load expenses.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [businessId, token, page, buildFilters, reloadKey]);

  // The summary depends on the filters but not the page, so paging doesn't refetch it.
  useEffect(() => {
    if (!token || !businessId) return;
    let cancelled = false;
    fetchExpenseSummary(businessId, buildFilters(), token)
      .then((result) => {
        if (!cancelled) setSummary(result);
      })
      .catch(() => {
        if (!cancelled) setSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [businessId, token, buildFilters, reloadKey]);

  const applyPreset = (next: Exclude<Preset, "custom">) => {
    const [start, end] = presetRange(next);
    setPreset(next);
    setStartDate(start);
    setEndDate(end);
    setPage(1);
  };

  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    setActiveQuery(searchText.trim());
    setPage(1);
  };

  const handleSaved = (_saved: Expense, mode: "created" | "updated") => {
    setFormTarget(null);
    setNotice({ kind: "success", text: mode === "created" ? "Expense added." : "Expense updated." });
    if (mode === "created") setPage(1);
    setReloadKey((k) => k + 1);
  };

  const handleDelete = async (expense: Expense) => {
    if (!token || !businessId) return;
    setDeletingId(expense.id);
    setNotice(null);
    try {
      await deleteExpense(businessId, expense.id, token);
      setConfirmingDeleteId(null);
      setNotice({ kind: "success", text: "Expense deleted." });
      // Deleting the only row on the last page would otherwise leave an empty page.
      if (data && data.items.length === 1 && page > 1) setPage(page - 1);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setNotice({ kind: "error", text: err instanceof ApiError ? err.message : "Could not delete this expense." });
    } finally {
      setDeletingId(null);
    }
  };

  if (isLoadingBusinesses) return <p className={styles.muted}>Loading…</p>;

  if (!primaryBusiness || !businessId) {
    return (
      <div>
        <h1 className={styles.title}>Expenses</h1>
        <p className={styles.muted}>Create a business on the Overview page before recording expenses.</p>
      </div>
    );
  }

  const branchNames = new Map(branches.map((b) => [b.id, b.name]));
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const hasFilters = Boolean(category || branchFilter || activeQuery);
  const topCategory = summary?.by_category[0];

  return (
    <div className={styles.page}>
      <div className={styles.headerRow}>
        <div>
          <h1 className={styles.title}>Expenses</h1>
          <p className={styles.subtitle}>
            Rent, salaries, transport and other running costs. They come off your gross profit to give your net
            profit.
          </p>
        </div>
        {canEdit && (
          <button type="button" className={styles.addButton} onClick={() => setFormTarget("new")}>
            + Add expense
          </button>
        )}
      </div>

      {currentUserRole !== null && !canEdit && (
        <p className={styles.muted}>Your role can view expenses but not add or change them.</p>
      )}

      {/* ---- Filters ---- */}
      <div className={styles.filters}>
        <div className={styles.presets} role="group" aria-label="Date range">
          {PRESET_LABELS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              className={`${styles.chip} ${preset === key ? styles.chipActive : ""}`}
              onClick={() => applyPreset(key)}
              aria-pressed={preset === key}
            >
              {label}
            </button>
          ))}
        </div>
        <div className={styles.filterRow}>
          <label className={styles.dateField}>
            <span>From</span>
            <input
              type="date"
              value={startDate}
              max={endDate || undefined}
              onChange={(e) => {
                setStartDate(e.target.value);
                setPreset("custom");
                setPage(1);
              }}
              className={styles.control}
            />
          </label>
          <label className={styles.dateField}>
            <span>To</span>
            <input
              type="date"
              value={endDate}
              min={startDate || undefined}
              onChange={(e) => {
                setEndDate(e.target.value);
                setPreset("custom");
                setPage(1);
              }}
              className={styles.control}
            />
          </label>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(1);
            }}
            className={styles.control}
            aria-label="Category"
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
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
              placeholder="Search category or note…"
              className={`${styles.control} ${styles.searchInput}`}
              aria-label="Search expenses"
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

      {/* ---- Summary ---- */}
      <div className={styles.summaryGrid}>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>Total spent</div>
          <div className={styles.statValue}>{summary ? currencyFormatter.format(Number(summary.total)) : "—"}</div>
          <div className={styles.statHint}>
            {summary ? `${summary.count} expense${summary.count === 1 ? "" : "s"}` : "Loading…"}
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statLabel}>Biggest category</div>
          <div className={styles.statValue}>{topCategory ? topCategory.category : "—"}</div>
          <div className={styles.statHint}>
            {topCategory
              ? `${currencyFormatter.format(Number(topCategory.total))} · ${Number(topCategory.share_percent)}% of the total`
              : "Nothing recorded for these filters"}
          </div>
        </div>
      </div>

      {summary && summary.by_category.length > 0 && (
        <div className={styles.breakdown}>
          <h2 className={styles.sectionTitle}>Where the money went</h2>
          <ul className={styles.barList}>
            {summary.by_category.map((c) => (
              <li key={c.category} className={styles.barRow}>
                <div className={styles.barTop}>
                  <span className={styles.barName}>{c.category}</span>
                  <span className={styles.barAmount}>
                    {currencyFormatter.format(Number(c.total))}
                    <span className={styles.barPercent}> · {Number(c.share_percent)}%</span>
                  </span>
                </div>
                <div className={styles.barTrack}>
                  <div className={styles.barFill} style={{ width: `${Math.max(2, Number(c.share_percent))}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {formTarget !== null && (
        <ExpenseFormModal
          businessId={businessId}
          expense={formTarget === "new" ? null : formTarget}
          categories={categories}
          branches={branches}
          onClose={() => setFormTarget(null)}
          onSaved={handleSaved}
        />
      )}

      {/* ---- List ---- */}
      {data && data.total === 0 && !isLoading ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>{hasFilters || preset !== "all" ? "No expenses match these filters" : "No expenses yet"}</p>
          <p className={styles.emptyBody}>
            {canEdit
              ? "Record what you spend on rent, salaries, transport and the like so your net profit reflects reality."
              : "Nothing has been recorded for this period."}
          </p>
          {canEdit && (
            <button type="button" className={styles.addButton} onClick={() => setFormTarget("new")}>
              + Add expense
            </button>
          )}
        </div>
      ) : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Category</th>
                  <th>Note</th>
                  {branches.length > 0 && <th>Branch</th>}
                  <th className={styles.numeric}>Amount</th>
                  {canEdit && <th>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {!data
                  ? Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i}>
                        <td colSpan={4 + (branches.length > 0 ? 1 : 0) + (canEdit ? 1 : 0)}>
                          <span className={styles.skeleton} />
                        </td>
                      </tr>
                    ))
                  : data.items.map((expense) => (
                      <tr key={expense.id}>
                        <td>{formatDate(expense.date)}</td>
                        <td className={styles.categoryCell}>{expense.category}</td>
                        <td className={styles.noteCell}>{expense.description ?? "—"}</td>
                        {branches.length > 0 && (
                          <td>{expense.branch_id ? (branchNames.get(expense.branch_id) ?? "—") : "Shared"}</td>
                        )}
                        <td className={styles.numeric}>{currencyFormatter.format(Number(expense.amount))}</td>
                        {canEdit && (
                          <td>
                            {confirmingDeleteId === expense.id ? (
                              <div className={styles.rowActions}>
                                <button
                                  type="button"
                                  className={styles.confirmDeleteButton}
                                  onClick={() => handleDelete(expense)}
                                  disabled={deletingId === expense.id}
                                >
                                  {deletingId === expense.id ? "Deleting…" : "Confirm delete"}
                                </button>
                                <button
                                  type="button"
                                  className={styles.rowButton}
                                  onClick={() => setConfirmingDeleteId(null)}
                                  disabled={deletingId === expense.id}
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
                                    setFormTarget(expense);
                                  }}
                                >
                                  Edit
                                </button>
                                {canDelete && (
                                  <button
                                    type="button"
                                    className={styles.rowDeleteButton}
                                    onClick={() => setConfirmingDeleteId(expense.id)}
                                  >
                                    Delete
                                  </button>
                                )}
                              </div>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>

          {data && (
            <div className={styles.pagination}>
              <span>
                {data.total} expense{data.total === 1 ? "" : "s"} · Page {data.page} of {totalPages}
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
