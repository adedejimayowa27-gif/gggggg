"use client";

/**
 * Bulk expense import (Step 13, Batch 3.1): the same upload -> map
 * columns -> confirm flow TransactionImportWizard uses, pointed at the
 * expense schema (date/category/amount/description/branch) instead.
 *
 * Built as its own component rather than a generalized/shared one with
 * TransactionImportWizard, to avoid any risk of changing that already-
 * shipped, tested component; the two intentionally share their CSS
 * module since they're meant to look identical.
 */
import { useEffect, useRef, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { downloadImportTemplate } from "@/lib/onboarding";
import type { ImportConfirmResult, ImportPreview } from "@/types";
import styles from "./TransactionImportWizard.module.css";

type Stage = "idle" | "uploading" | "mapping" | "confirming" | "result";

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 2 * 60 * 1000;

const EXPENSE_FIELDS = ["date", "category", "amount", "description", "branch"] as const;
type ExpenseField = (typeof EXPENSE_FIELDS)[number];

const FIELD_LABELS: Record<ExpenseField, string> = {
  date: "Date",
  category: "Category",
  amount: "Amount",
  description: "Note / Description",
  branch: "Branch",
};

const OPTIONAL_FIELDS: ExpenseField[] = ["description", "branch"];

type ExpenseColumnMapping = Record<ExpenseField, string | null>;

interface Props {
  businessId: string;
  onImportComplete?: () => void;
}

export default function ExpenseImportWizard({ businessId, onImportComplete }: Props) {
  const { token } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const unmountedRef = useRef(false);
  useEffect(() => {
    return () => {
      unmountedRef.current = true;
    };
  }, []);

  const [stage, setStage] = useState<Stage>("idle");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<ExpenseColumnMapping | null>(null);
  const [result, setResult] = useState<ImportConfirmResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDownloadingTemplate, setIsDownloadingTemplate] = useState(false);

  const handleDownloadTemplate = async () => {
    if (!token) return;
    setIsDownloadingTemplate(true);
    try {
      await downloadImportTemplate(businessId, "expenses", token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download the template.");
    } finally {
      setIsDownloadingTemplate(false);
    }
  };

  const reset = () => {
    setStage("idle");
    setSelectedFile(null);
    setPreview(null);
    setMapping(null);
    setResult(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile || !token) return;
    setError(null);
    setStage("uploading");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const data = await apiFetch<ImportPreview>(
        `/businesses/${businessId}/imports/upload?target=expenses`,
        { method: "POST", authToken: token, body: formData }
      );
      setPreview(data);
      setMapping(data.suggested_mapping as unknown as ExpenseColumnMapping);
      setStage("mapping");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Please try again.");
      setStage("idle");
    }
  };

  const handleMappingChange = (field: ExpenseField, column: string) => {
    setMapping((prev) => (prev ? { ...prev, [field]: column || null } : prev));
  };

  const handleConfirm = async () => {
    if (!preview || !mapping || !token) return;
    setError(null);
    setStage("confirming");
    try {
      await apiFetch<ImportConfirmResult>(`/businesses/${businessId}/imports/${preview.id}/confirm`, {
        method: "POST",
        authToken: token,
        body: JSON.stringify({ mapping }),
      });

      const startedAt = Date.now();
      const poll = async (): Promise<void> => {
        if (unmountedRef.current) return;
        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          setError(
            "This import is taking longer than expected. It's still processing in the background -- check the import history shortly."
          );
          setStage("mapping");
          return;
        }
        const current = await apiFetch<ImportConfirmResult>(`/businesses/${businessId}/imports/${preview.id}`, {
          authToken: token,
        });
        if (unmountedRef.current) return;
        if (current.status === "completed" || current.status === "failed") {
          setResult(current);
          setStage("result");
          onImportComplete?.();
          return;
        }
        setTimeout(poll, POLL_INTERVAL_MS);
      };
      setTimeout(poll, POLL_INTERVAL_MS);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not confirm import.");
      setStage("mapping");
    }
  };

  const requiredFieldsMapped =
    mapping && EXPENSE_FIELDS.filter((f) => !OPTIONAL_FIELDS.includes(f)).every((f) => mapping[f]);

  const currentStep =
    stage === "idle" || stage === "uploading" ? 1 : stage === "mapping" || stage === "confirming" ? 2 : 3;

  return (
    <div className={styles.wrap}>
      <div className={styles.steps}>
        {["Upload", "Map columns", "Done"].map((label, i) => {
          const step = i + 1;
          return (
            <div key={label} className={styles.step}>
              <span
                className={`${styles.stepDot} ${
                  step < currentStep ? styles.stepDotDone : step === currentStep ? styles.stepDotActive : ""
                }`}
              >
                {step < currentStep ? "✓" : step}
              </span>
              <span className={step === currentStep ? styles.stepLabelActive : styles.stepLabel}>{label}</span>
              {step < 3 && <span className={styles.stepLine} />}
            </div>
          );
        })}
      </div>

      {stage === "idle" && (
        <div
          className={`${styles.dropzone} ${isDragOver ? styles.dropzoneActive : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragOver(true);
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleDrop}
        >
          <h2>Upload an expenses file</h2>
          <p>Drag and drop, or choose a file -- accepts .xlsx or .csv, up to 5MB and 5,000 rows.</p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.xlsx"
            onChange={handleFileChange}
            className={styles.fileInput}
            id="expense-file-input"
          />
          <label htmlFor="expense-file-input" className={styles.chooseButton}>
            Choose file
          </label>
          {selectedFile && <div className={styles.fileName}>{selectedFile.name}</div>}
          <div>
            <button className={styles.uploadButton} onClick={handleUpload} disabled={!selectedFile}>
              Upload and preview
            </button>
          </div>
          <p className={styles.templateRow}>
            Not sure how to lay out your file?{" "}
            <button
              type="button"
              className={styles.templateLink}
              onClick={handleDownloadTemplate}
              disabled={isDownloadingTemplate}
            >
              {isDownloadingTemplate ? "Preparing…" : "Download a blank template"}
            </button>
          </p>
          {error && <p className={styles.error}>{error}</p>}
        </div>
      )}

      {stage === "uploading" && (
        <div className={styles.dropzone}>
          <p>Uploading and parsing your file…</p>
        </div>
      )}

      {(stage === "mapping" || stage === "confirming") && preview && mapping && (
        <div>
          <div className={styles.section}>
            <div className={styles.sectionTitle}>
              Preview — {preview.total_row_count} row{preview.total_row_count === 1 ? "" : "s"} detected in{" "}
              {preview.filename}
            </div>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    {preview.detected_columns.map((col) => (
                      <th key={col}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.preview_rows.map((row, i) => (
                    <tr key={i}>
                      {preview.detected_columns.map((col) => (
                        <td key={col}>{String(row[col] ?? "")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className={styles.section}>
            <div className={styles.sectionTitle}>Map your columns</div>
            <div className={styles.mappingGrid}>
              {EXPENSE_FIELDS.map((field) => (
                <div key={field} className={styles.mappingRow}>
                  <label className={styles.mappingLabel}>
                    {FIELD_LABELS[field]}
                    {OPTIONAL_FIELDS.includes(field) && <span className={styles.mappingOptional}> (optional)</span>}
                  </label>
                  <select
                    className={styles.select}
                    value={mapping[field] ?? ""}
                    onChange={(e) => handleMappingChange(field, e.target.value)}
                  >
                    <option value="">{OPTIONAL_FIELDS.includes(field) ? "-- Not in file --" : "-- Select column --"}</option>
                    {preview.detected_columns.map((col) => (
                      <option key={col} value={col}>
                        {col}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>

            {error && <p className={styles.error}>{error}</p>}

            <div>
              <button
                className={styles.confirmButton}
                onClick={handleConfirm}
                disabled={!requiredFieldsMapped || stage === "confirming"}
              >
                {stage === "confirming" ? "Importing… (this runs in the background, hang tight)" : "Confirm and import"}
              </button>
              <button className={styles.cancelButton} onClick={reset} disabled={stage === "confirming"}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {stage === "result" && result && (
        <div className={styles.section}>
          <div className={styles.resultSummary}>
            <div className={styles.resultStat}>
              <div className={`${styles.resultStatValue} ${styles.successValue}`}>{result.imported_row_count ?? 0}</div>
              <div className={styles.resultStatLabel}>Imported</div>
            </div>
            <div className={styles.resultStat}>
              <div className={`${styles.resultStatValue} ${styles.failValue}`}>{result.failed_row_count ?? 0}</div>
              <div className={styles.resultStatLabel}>Failed</div>
            </div>
            <div className={styles.resultStat}>
              <div className={styles.resultStatValue}>{result.total_row_count}</div>
              <div className={styles.resultStatLabel}>Total rows</div>
            </div>
          </div>

          {result.row_errors.length > 0 && (
            <div>
              <div className={styles.sectionTitle}>Rows that couldn&apos;t be imported</div>
              <div className={styles.errorList}>
                {result.row_errors.map((rowError) => (
                  <div key={rowError.row_number} className={styles.errorRow}>
                    <span className={styles.errorRowNumber}>Row {rowError.row_number}</span>
                    <div className={styles.errorMessages}>{rowError.errors.join(" ")}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <button className={styles.uploadButton} onClick={reset}>
              Upload another file
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
