"use client";

/**
 * Add a sale by hand, or correct an existing one (Step 13, Batch 1).
 *
 * One form for both: pass `transaction` to edit, leave it out to add. The
 * backend re-validates everything (and is the real gatekeeper for who may
 * do this); the checks here just save a round trip for the obvious
 * mistakes -- an empty product, a zero quantity, a negative price.
 */
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { createTransaction, fetchFieldValues, updateTransaction } from "@/lib/transactions";
import type { TransactionInput } from "@/lib/transactions";
import type { Branch, Transaction } from "@/types";
import styles from "./TransactionFormModal.module.css";

interface Props {
  businessId: string;
  /** Present = editing this transaction; absent = adding a new one. */
  transaction?: Transaction | null;
  branches: Branch[];
  onClose: () => void;
  /** Called after a successful save, with what the server stored. */
  onSaved: (saved: Transaction, mode: "created" | "updated") => void;
}

const DEFAULT_PAYMENT_METHODS = ["Cash", "Transfer", "POS", "Card"];

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  minimumFractionDigits: 2,
});

/** Today's date in the person's own timezone, as YYYY-MM-DD. (toISOString
 * would give the UTC date, which can be yesterday or tomorrow locally.) */
function todayLocalISO(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/** Drops needless trailing zeros ("2.500" -> "2.5") for editing; the server
 * stores fixed precision, which is noise in an input box. */
function trimNumber(value: string | null): string {
  if (value === null || value === "") return "";
  const n = Number(value);
  return Number.isFinite(n) ? String(n) : value;
}

function isPositive(value: string): boolean {
  const n = Number(value);
  return value.trim() !== "" && Number.isFinite(n) && n > 0;
}

function isNonNegative(value: string): boolean {
  const n = Number(value);
  return value.trim() !== "" && Number.isFinite(n) && n >= 0;
}

interface FieldErrors {
  date?: string;
  product?: string;
  quantity?: string;
  selling_price?: string;
  cost_price?: string;
}

export default function TransactionFormModal({ businessId, transaction, branches, onClose, onSaved }: Props) {
  const { token } = useAuth();
  const isEditing = Boolean(transaction);

  const [date, setDate] = useState(transaction?.date ?? todayLocalISO());
  const [product, setProduct] = useState(transaction?.product ?? "");
  const [quantity, setQuantity] = useState(trimNumber(transaction?.quantity ?? "1"));
  const [sellingPrice, setSellingPrice] = useState(trimNumber(transaction?.selling_price ?? ""));
  const [costPrice, setCostPrice] = useState(trimNumber(transaction?.cost_price ?? ""));
  const [category, setCategory] = useState(transaction?.category ?? "");
  const [customer, setCustomer] = useState(transaction?.customer ?? "");
  const [paymentMethod, setPaymentMethod] = useState(transaction?.payment_method ?? "");
  const [branchId, setBranchId] = useState(transaction?.branch_id ?? "");

  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const [productOptions, setProductOptions] = useState<string[]>([]);
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const [customerOptions, setCustomerOptions] = useState<string[]>([]);
  const [paymentOptions, setPaymentOptions] = useState<string[]>(DEFAULT_PAYMENT_METHODS);

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

  // Suggestions come from what this business has already recorded, so the
  // same product/customer is spelled the same way every time.
  useEffect(() => {
    if (!token) return;
    const load = (field: "product" | "category" | "customer" | "payment_method") =>
      fetchFieldValues(businessId, field, token).catch(() => [] as string[]);
    Promise.all([load("product"), load("category"), load("customer"), load("payment_method")]).then(
      ([products, categories, customers, payments]) => {
        setProductOptions(products);
        setCategoryOptions(categories);
        setCustomerOptions(customers);
        const merged = [...DEFAULT_PAYMENT_METHODS];
        for (const p of payments) {
          if (!merged.some((m) => m.toLowerCase() === p.toLowerCase())) merged.push(p);
        }
        setPaymentOptions(merged);
      }
    );
  }, [businessId, token]);

  const preview = useMemo(() => {
    if (!isPositive(quantity) || !isNonNegative(sellingPrice)) return null;
    const revenue = Number(quantity) * Number(sellingPrice);
    const profit = isNonNegative(costPrice) ? revenue - Number(quantity) * Number(costPrice) : null;
    return { revenue, profit };
  }, [quantity, sellingPrice, costPrice]);

  const validate = (): FieldErrors => {
    const errors: FieldErrors = {};
    if (!date) {
      errors.date = "Pick the date of the sale.";
    } else {
      const latest = new Date();
      latest.setDate(latest.getDate() + 1);
      const latestISO = `${latest.getFullYear()}-${String(latest.getMonth() + 1).padStart(2, "0")}-${String(latest.getDate()).padStart(2, "0")}`;
      if (date > latestISO) errors.date = "The date can't be in the future.";
      else if (date < "2000-01-01") errors.date = "That date looks too far in the past.";
    }
    if (!product.trim()) errors.product = "Enter what was sold.";
    if (!isPositive(quantity)) errors.quantity = "Quantity must be more than zero.";
    if (!isNonNegative(sellingPrice)) errors.selling_price = "Enter the price per item (0 or more).";
    if (costPrice.trim() !== "" && !isNonNegative(costPrice)) {
      errors.cost_price = "Cost can't be negative.";
    }
    return errors;
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token || isSaving) return;

    const errors = validate();
    setFieldErrors(errors);
    setFormError(null);
    if (Object.keys(errors).length > 0) return;

    const input: TransactionInput = {
      date,
      product: product.trim(),
      quantity: quantity.trim(),
      selling_price: sellingPrice.trim(),
      cost_price: costPrice.trim() === "" ? null : costPrice.trim(),
      category: category.trim() === "" ? null : category.trim(),
      customer: customer.trim() === "" ? null : customer.trim(),
      payment_method: paymentMethod.trim() === "" ? null : paymentMethod.trim(),
      branch_id: branchId === "" ? null : branchId,
    };

    setIsSaving(true);
    try {
      if (transaction) {
        const saved = await updateTransaction(businessId, transaction.id, input, token);
        onSaved(saved, "updated");
      } else {
        const saved = await createTransaction(businessId, input, token);
        onSaved(saved, "created");
      }
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not save this sale. Please try again.");
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
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="transaction-form-title"
      >
        <div className={styles.header}>
          <h2 id="transaction-form-title" className={styles.title}>
            {isEditing ? "Edit sale" : "Add a sale"}
          </h2>
          <button type="button" className={styles.closeButton} onClick={onClose} aria-label="Close" disabled={isSaving}>
            ×
          </button>
        </div>

        {isEditing && transaction?.import_session_id && (
          <p className={styles.note}>
            This sale was imported. Your changes here are kept — a future import or sync won&apos;t
            overwrite them or add the original row back.
          </p>
        )}

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

            <label className={`${styles.field} ${styles.wide}`}>
              <span className={styles.label}>Product</span>
              <input
                type="text"
                list="txn-products"
                value={product}
                onChange={(e) => setProduct(e.target.value)}
                className={styles.input}
                maxLength={255}
                placeholder="e.g. Bag of rice (50kg)"
                aria-invalid={Boolean(fieldErrors.product)}
                required
              />
              <datalist id="txn-products">
                {productOptions.map((p) => (
                  <option key={p} value={p} />
                ))}
              </datalist>
              {fieldErrors.product && <span className={styles.error}>{fieldErrors.product}</span>}
            </label>

            <label className={styles.field}>
              <span className={styles.label}>Quantity</span>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="any"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className={styles.input}
                aria-invalid={Boolean(fieldErrors.quantity)}
                required
              />
              {fieldErrors.quantity && <span className={styles.error}>{fieldErrors.quantity}</span>}
            </label>

            <label className={styles.field}>
              <span className={styles.label}>Selling price (each, ₦)</span>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="any"
                value={sellingPrice}
                onChange={(e) => setSellingPrice(e.target.value)}
                className={styles.input}
                aria-invalid={Boolean(fieldErrors.selling_price)}
                required
              />
              {fieldErrors.selling_price && <span className={styles.error}>{fieldErrors.selling_price}</span>}
            </label>

            <label className={styles.field}>
              <span className={styles.label}>
                Cost price (each, ₦) <span className={styles.optional}>optional</span>
              </span>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="any"
                value={costPrice}
                onChange={(e) => setCostPrice(e.target.value)}
                className={styles.input}
                aria-invalid={Boolean(fieldErrors.cost_price)}
              />
              {fieldErrors.cost_price && <span className={styles.error}>{fieldErrors.cost_price}</span>}
            </label>

            <label className={styles.field}>
              <span className={styles.label}>
                Category <span className={styles.optional}>optional</span>
              </span>
              <input
                type="text"
                list="txn-categories"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className={styles.input}
                maxLength={255}
              />
              <datalist id="txn-categories">
                {categoryOptions.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </label>

            <label className={styles.field}>
              <span className={styles.label}>
                Customer <span className={styles.optional}>optional</span>
              </span>
              <input
                type="text"
                list="txn-customers"
                value={customer}
                onChange={(e) => setCustomer(e.target.value)}
                className={styles.input}
                maxLength={255}
              />
              <datalist id="txn-customers">
                {customerOptions.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </label>

            <label className={styles.field}>
              <span className={styles.label}>
                Payment method <span className={styles.optional}>optional</span>
              </span>
              <input
                type="text"
                list="txn-payments"
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value)}
                className={styles.input}
                maxLength={100}
              />
              <datalist id="txn-payments">
                {paymentOptions.map((p) => (
                  <option key={p} value={p} />
                ))}
              </datalist>
            </label>

            {branches.length > 0 && (
              <label className={styles.field}>
                <span className={styles.label}>
                  Branch <span className={styles.optional}>optional</span>
                </span>
                <select value={branchId} onChange={(e) => setBranchId(e.target.value)} className={styles.input}>
                  <option value="">No branch</option>
                  {branches.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {preview && (
            <p className={styles.preview} aria-live="polite">
              Sale total <strong>{currencyFormatter.format(preview.revenue)}</strong>
              {preview.profit !== null && (
                <>
                  {" · "}Profit <strong>{currencyFormatter.format(preview.profit)}</strong>
                </>
              )}
            </p>
          )}

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
              {isSaving ? "Saving…" : isEditing ? "Save changes" : "Add sale"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
