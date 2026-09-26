"use client";

/**
 * Start tracking a product's stock, or edit reorder level / branch for one
 * (Step 13, Batch 3). Quantity on hand is deliberately not editable here --
 * see StockAdjustmentModal for restock/damage/correction, which always
 * leave an audit trail.
 */
import { FormEvent, useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { createStock, updateStock } from "@/lib/stock";
import type { StockInput } from "@/lib/stock";
import type { Branch, Stock } from "@/types";
import styles from "./TransactionFormModal.module.css";

interface Props {
  businessId: string;
  /** Present = editing this record's reorder level/branch; absent = tracking a new product. */
  stock?: Stock | null;
  branches: Branch[];
  onClose: () => void;
  onSaved: (saved: Stock, mode: "created" | "updated") => void;
}

interface FieldErrors {
  product?: string;
  quantity_on_hand?: string;
  reorder_level?: string;
}

export default function StockFormModal({ businessId, stock, branches, onClose, onSaved }: Props) {
  const { token } = useAuth();
  const isEditing = Boolean(stock);

  const [product, setProduct] = useState(stock?.product ?? "");
  const [quantityOnHand, setQuantityOnHand] = useState(stock?.quantity_on_hand ?? "0");
  const [reorderLevel, setReorderLevel] = useState(stock?.reorder_level ?? "0");
  const [branchId, setBranchId] = useState(stock?.branch_id ?? "");

  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const firstFieldRef = useRef<HTMLInputElement>(null);

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

  const isNonNegative = (value: string): boolean => {
    const n = Number(value);
    return value.trim() !== "" && Number.isFinite(n) && n >= 0;
  };

  const validate = (): FieldErrors => {
    const errors: FieldErrors = {};
    if (!product.trim()) errors.product = "Enter a product name.";
    if (!isEditing && !isNonNegative(quantityOnHand)) errors.quantity_on_hand = "Enter 0 or more.";
    if (!isNonNegative(reorderLevel)) errors.reorder_level = "Enter 0 or more.";
    return errors;
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token || isSaving) return;

    const errors = validate();
    setFieldErrors(errors);
    setFormError(null);
    if (Object.keys(errors).length > 0) return;

    setIsSaving(true);
    try {
      if (stock) {
        const saved = await updateStock(
          businessId, stock.id,
          { reorder_level: reorderLevel.trim(), branch_id: branchId === "" ? null : branchId },
          token
        );
        onSaved(saved, "updated");
      } else {
        const input: StockInput = {
          product: product.trim(),
          branch_id: branchId === "" ? null : branchId,
          quantity_on_hand: quantityOnHand.trim(),
          reorder_level: reorderLevel.trim(),
        };
        const saved = await createStock(businessId, input, token);
        onSaved(saved, "created");
      }
    } catch (err) {
      setFormError(
        err instanceof ApiError
          ? err.message
          : "Could not save this stock record. Please try again."
      );
      setIsSaving(false);
    }
  };

  return (
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSaving) onClose();
      }}
    >
      <div className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="stock-form-title">
        <div className={styles.header}>
          <h2 id="stock-form-title" className={styles.title}>
            {isEditing ? "Edit stock settings" : "Track a product's stock"}
          </h2>
          <button type="button" className={styles.closeButton} onClick={onClose} aria-label="Close" disabled={isSaving}>
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          <div className={styles.grid}>
            <label className={`${styles.field} ${styles.wide}`}>
              <span className={styles.label}>Product</span>
              <input
                ref={firstFieldRef}
                type="text"
                value={product}
                onChange={(e) => setProduct(e.target.value)}
                className={styles.input}
                maxLength={255}
                placeholder="e.g. Bag of rice (50kg)"
                aria-invalid={Boolean(fieldErrors.product)}
                disabled={isEditing}
                required
              />
              {isEditing && (
                <span className={styles.optional} style={{ marginTop: "0.2rem" }}>
                  The product name can&apos;t be changed here -- delete this record and add a new one instead.
                </span>
              )}
              {fieldErrors.product && <span className={styles.error}>{fieldErrors.product}</span>}
            </label>

            {!isEditing && (
              <label className={styles.field}>
                <span className={styles.label}>Starting quantity</span>
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step="any"
                  value={quantityOnHand}
                  onChange={(e) => setQuantityOnHand(e.target.value)}
                  className={styles.input}
                  aria-invalid={Boolean(fieldErrors.quantity_on_hand)}
                  required
                />
                {fieldErrors.quantity_on_hand && <span className={styles.error}>{fieldErrors.quantity_on_hand}</span>}
              </label>
            )}

            <label className={styles.field}>
              <span className={styles.label}>
                Reorder level <span className={styles.optional}>alert when at or below this</span>
              </span>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="any"
                value={reorderLevel}
                onChange={(e) => setReorderLevel(e.target.value)}
                className={styles.input}
                placeholder="0 = don't alert"
                aria-invalid={Boolean(fieldErrors.reorder_level)}
              />
              {fieldErrors.reorder_level && <span className={styles.error}>{fieldErrors.reorder_level}</span>}
            </label>

            {branches.length > 0 && (
              <label className={`${styles.field} ${styles.wide}`}>
                <span className={styles.label}>
                  Branch <span className={styles.optional}>leave empty for one shared stock list</span>
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
              {isSaving ? "Saving…" : isEditing ? "Save changes" : "Start tracking"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
