"use client";

/**
 * Restock, record damage/loss, or correct a count for one stock record,
 * plus its adjustment history (Step 13, Batch 3). This is the only way
 * quantity_on_hand ever changes by hand, so every change is logged.
 */
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { createStockAdjustment, listStockAdjustments } from "@/lib/stock";
import type { Stock, StockAdjustment, StockAdjustmentReason } from "@/types";
import styles from "./TransactionFormModal.module.css";
import historyStyles from "./StockAdjustmentModal.module.css";

interface Props {
  businessId: string;
  stock: Stock;
  onClose: () => void;
  onSaved: (saved: Stock) => void;
}

const REASON_LABELS: Record<StockAdjustmentReason, string> = {
  restock: "Restock (add)",
  damage: "Damage / loss (remove)",
  correction: "Correction (set exact count)",
};

const dateFormatter = new Intl.DateTimeFormat("en-NG", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

function formatWhen(value: string): string {
  return dateFormatter.format(new Date(value));
}

function reasonLabel(reason: string): string {
  if (reason === "initial") return "Starting quantity";
  if (reason === "sale") return "Sale";
  if (reason === "sale_reversal") return "Sale reversed";
  return REASON_LABELS[reason as StockAdjustmentReason] ?? reason;
}

export default function StockAdjustmentModal({ businessId, stock, onClose, onSaved }: Props) {
  const { token } = useAuth();
  const [reason, setReason] = useState<StockAdjustmentReason>("restock");
  const [quantity, setQuantity] = useState("");
  const [note, setNote] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [currentStock, setCurrentStock] = useState(stock);

  const [history, setHistory] = useState<StockAdjustment[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

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

  const loadHistory = () => {
    if (!token) return;
    listStockAdjustments(businessId, currentStock.id, token)
      .then(setHistory)
      .catch(() => setHistoryError("Could not load history."));
  };

  useEffect(() => {
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId, currentStock.id, token]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token || isSaving) return;

    const n = Number(quantity);
    if (quantity.trim() === "" || !Number.isFinite(n) || (reason === "correction" ? n < 0 : n <= 0)) {
      setFieldError(reason === "correction" ? "Enter the exact count (0 or more)." : "Enter an amount more than zero.");
      return;
    }
    setFieldError(null);
    setFormError(null);
    setIsSaving(true);
    try {
      const result = await createStockAdjustment(
        businessId, currentStock.id, reason, quantity.trim(), note.trim() === "" ? null : note.trim(), token
      );
      setCurrentStock(result.stock);
      setQuantity("");
      setNote("");
      onSaved(result.stock);
      loadHistory();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not save this adjustment. Please try again.");
    } finally {
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
      <div className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="stock-adjustment-title">
        <div className={styles.header}>
          <h2 id="stock-adjustment-title" className={styles.title}>
            {currentStock.product}
          </h2>
          <button type="button" className={styles.closeButton} onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <p className={historyStyles.currentQty}>
          On hand: <strong>{Number(currentStock.quantity_on_hand)}</strong>
          {currentStock.is_low && <span className={historyStyles.lowBadge}>Low</span>}
        </p>

        <form onSubmit={handleSubmit} noValidate>
          <div className={styles.grid}>
            <label className={`${styles.field} ${styles.wide}`}>
              <span className={styles.label}>Type</span>
              <select
                value={reason}
                onChange={(e) => setReason(e.target.value as StockAdjustmentReason)}
                className={styles.input}
              >
                {(Object.keys(REASON_LABELS) as StockAdjustmentReason[]).map((r) => (
                  <option key={r} value={r}>
                    {REASON_LABELS[r]}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.field}>
              <span className={styles.label}>{reason === "correction" ? "New exact count" : "Quantity"}</span>
              <input
                ref={firstFieldRef}
                type="number"
                inputMode="decimal"
                min="0"
                step="any"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className={styles.input}
                aria-invalid={Boolean(fieldError)}
                required
              />
              {fieldError && <span className={styles.error}>{fieldError}</span>}
            </label>

            <label className={`${styles.field} ${styles.wide}`}>
              <span className={styles.label}>
                Note <span className={styles.optional}>optional</span>
              </span>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className={styles.input}
                maxLength={255}
                placeholder="What happened?"
              />
            </label>
          </div>

          {formError && (
            <p className={styles.formError} role="alert">
              {formError}
            </p>
          )}

          <div className={styles.actions}>
            <button type="button" className={styles.cancelButton} onClick={onClose} disabled={isSaving}>
              Close
            </button>
            <button type="submit" className={styles.saveButton} disabled={isSaving}>
              {isSaving ? "Saving…" : "Save adjustment"}
            </button>
          </div>
        </form>

        <div className={historyStyles.historySection}>
          <h3 className={historyStyles.historyTitle}>History</h3>
          {historyError && <p className={styles.error}>{historyError}</p>}
          {!history && !historyError && <p className={historyStyles.muted}>Loading…</p>}
          {history && history.length === 0 && <p className={historyStyles.muted}>No adjustments yet.</p>}
          {history && history.length > 0 && (
            <ul className={historyStyles.historyList}>
              {history.map((h) => (
                <li key={h.id} className={historyStyles.historyRow}>
                  <div>
                    <span className={historyStyles.historyReason}>{reasonLabel(h.reason)}</span>
                    {h.note && <span className={historyStyles.historyNote}> — {h.note}</span>}
                  </div>
                  <div className={historyStyles.historyRight}>
                    <span className={Number(h.delta) >= 0 ? historyStyles.deltaPositive : historyStyles.deltaNegative}>
                      {Number(h.delta) >= 0 ? "+" : ""}
                      {Number(h.delta)}
                    </span>
                    <span className={historyStyles.historyWhen}>{formatWhen(h.created_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
