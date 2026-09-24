"use client";

/**
 * Add an operating expense, or correct one (Step 13, Batch 2).
 *
 * One form for both: pass `expense` to edit, leave it out to add. Shares
 * its look with the sale form (same stylesheet), and like it the backend
 * re-validates everything -- the checks here only save a round trip.
 */
import { FormEvent, useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { createExpense, updateExpense } from "@/lib/expenses";
import type { ExpenseInput } from "@/lib/expenses";
import type { Branch, Expense } from "@/types";
import styles from "./TransactionFormModal.module.css";

interface Props {
  businessId: string;
  /** Present = editing this expense; absent = adding a new one. */
  expense?: Expense | null;
  /** Categories to suggest (already-used ones first, then common defaults). */
  categories: string[];
  branches: Branch[];
  onClose: () => void;
  onSaved: (saved: Expense, mode: "created" | "updated") => void;
}

/** Today's date in the person's own timezone as YYYY-MM-DD (toISOString
 * would give the UTC date, which can be a day off locally). */
function todayLocalISO(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function trimNumber(value: string | null | undefined): string {
  if (!value) return "";
  const n = Number(value);
  return Number.isFinite(n) ? String(n) : value;
}

interface FieldErrors {
  date?: string;
  category?: string;
  amount?: string;
}

export default function ExpenseFormModal({ businessId, expense, categories, branches, onClose, onSaved }: Props) {
  const { token } = useAuth();
  const isEditing = Boolean(expense);

  const [date, setDate] = useState(expense?.date ?? todayLocalISO());
  const [category, setCategory] = useState(expense?.category ?? "");
  const [amount, setAmount] = useState(trimNumber(expense?.amount));
  const [description, setDescription] = useState(expense?.description ?? "");
  const [branchId, setBranchId] = useState(expense?.branch_id ?? "");

  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  // Focus the first field on open; close on Escape; stop the page behind
  // from scrolling while the dialog is up.
  useEffect(() => {
    firstFieldRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const validate = (): FieldErrors => {
    const errors: FieldErrors = {};
    if (!date) {
      errors.date = "Pick the date of the expense.";
    } else {
      const latest = new Date();
      latest.setDate(latest.getDate() + 1);
      const latestISO = `${latest.getFullYear()}-${String(latest.getMonth() + 1).padStart(2, "0")}-${String(latest.getDate()).padStart(2, "0")}`;
      if (date > latestISO) errors.date = "The date can't be in the future.";
      else if (date < "2000-01-01") errors.date = "That date looks too far in the past.";
    }
    if (!category.trim()) errors.category = "Choose or type a category.";
    const n = Number(amount);
    if (amount.trim() === "" || !Number.isFinite(n) || n <= 0) errors.amount = "Amount must be more than zero.";
    return errors;
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token || isSaving) return;

    const errors = validate();
    setFieldErrors(errors);
    setFormError(null);
    if (Object.keys(errors).length > 0) return;

    const input: ExpenseInput = {
      date,
      category: category.trim(),
      amount: amount.trim(),
      description: description.trim() === "" ? null : description.trim(),
      branch_id: branchId === "" ? null : branchId,
    };

    setIsSaving(true);
    try {
      if (expense) {
        onSaved(await updateExpense(businessId, expense.id, input, token), "updated");
      } else {
        onSaved(await createExpense(businessId, input, token), "created");
      }
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not save this expense. Please try again.");
      setIsSaving(false);
    }
  };

  return (
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        // Only a click that starts on the backdrop itself closes it, so
        // dragging a text selection out of an input doesn't dismiss the form.
        if (event.target === event.currentTarget && !isSaving) onClose();
      }}
    >
      <div className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="expense-form-title">
        <div className={styles.header}>
          <h2 id="expense-form-title" className={styles.title}>
            {isEditing ? "Edit expense" : "Add an expense"}
          </h2>
          <button type="button" className={styles.closeButton} onClick={onClose} aria-label="Close" disabled={isSaving}>
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          <div className={styles.grid}>
            <label className={styles.field}>
              <span className={styles.label}>Date</span>
              <input
                ref={firstFieldRef}
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className={styles.input}
                aria-invalid={Boolean(fieldErrors.date)}
                required
              />
              {fieldErrors.date && <span className={styles.error}>{fieldErrors.date}</span>}
            </label>

            <label className={styles.field}>
              <span className={styles.label}>Amount (₦)</span>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="any"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className={styles.input}
                placeholder="e.g. 150000"
                aria-invalid={Boolean(fieldErrors.amount)}
                required
              />
              {fieldErrors.amount && <span className={styles.error}>{fieldErrors.amount}</span>}
            </label>

            <label className={`${styles.field} ${styles.wide}`}>
              <span className={styles.label}>Category</span>
              <input
                type="text"
                list="expense-categories"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className={styles.input}
                maxLength={100}
                placeholder="e.g. Rent, Salaries & wages, Transport & fuel"
                aria-invalid={Boolean(fieldErrors.category)}
                required
              />
              <datalist id="expense-categories">
                {categories.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
              {fieldErrors.category && <span className={styles.error}>{fieldErrors.category}</span>}
            </label>

            <label className={`${styles.field} ${styles.wide}`}>
              <span className={styles.label}>
                Note <span className={styles.optional}>optional</span>
              </span>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className={styles.input}
                maxLength={255}
                placeholder="What was it for?"
              />
            </label>

            {branches.length > 0 && (
              <label className={`${styles.field} ${styles.wide}`}>
                <span className={styles.label}>
                  Branch <span className={styles.optional}>optional — leave empty for shared costs</span>
                </span>
                <select value={branchId} onChange={(e) => setBranchId(e.target.value)} className={styles.input}>
                  <option value="">Shared across the business</option>
                  {branches.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {formError && (
            <p className={styles.formError} role="alert">
              {formError}
            </p>
          )}

          <div className={styles.actions}>
            <button type="button" className={styles.cancelButton} onClick={onClose} disabled={isSaving}>
              Cancel
            </button>
            <button type="submit" className={styles.saveButton} disabled={isSaving}>
              {isSaving ? "Saving…" : isEditing ? "Save changes" : "Add expense"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
