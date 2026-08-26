"use client";

import { useRef, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
  STANDARD_FIELDS,
  type ColumnMapping,
  type ImportConfirmResult,
  type ImportPreview,
  type StandardField,
} from "@/types";
import styles from "./TransactionImportWizard.module.css";

type Stage = "idle" | "uploading" | "mapping" | "confirming" | "result";

const FIELD_LABELS: Record<StandardField, string> = {
  date: "Date",
  product: "Product",
  quantity: "Quantity",
  selling_price: "Selling Price",
  cost_price: "Cost Price",
};

const OPTIONAL_FIELDS: StandardField[] = ["cost_price"];

interface Props {
  businessId: string;
  onImportComplete?: () => void;
}

export default function TransactionImportWizard({ businessId, onImportComplete }: Props) {
  const { token } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [stage, setStage] = useState<Stage>("idle");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [result, setResult] = useState<ImportConfirmResult | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const handleUpload = async () => {
    if (!selectedFile || !token) return;
    setError(null);
    setStage("uploading");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const data = await apiFetch<ImportPreview>(
        `/businesses/${businessId}/imports/upload`,
        { method: "POST", authToken: token, body: formData }
      );
      setPreview(data);
      setMapping(data.suggested_mapping);
      setStage("mapping");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Please try again.");
      setStage("idle");
    }
  };

  const handleMappingChange = (field: StandardField, column: string) => {
    setMapping((prev) => (prev ? { ...prev, [field]: column || null } : prev));
  };

  const handleConfirm = async () => {
    if (!preview || !mapping || !token) return;
    setError(null);
    setStage("confirming");
    try {
      const data = await apiFetch<ImportConfirmResult>(
        `/businesses/${businessId}/imports/${preview.id}/confirm`,
        {
          method: "POST",
          authToken: token,
          body: JSON.stringify({ mapping }),
        }
      );
      setResult(data);
      setStage("result");
      onImportComplete?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not confirm import.");
      setStage("mapping");
    }
  };

  const requiredFieldsMapped =
    mapping &&
    STANDARD_FIELDS.filter((f) => !OPTIONAL_FIELDS.includes(f)).every((f) => mapping[f]);

  return (
    <div className={styles.wrap}>
      {stage === "idle" && (
        <div className={styles.dropzone}>
          <h2>Upload a transactions file</h2>
          <p>Accepts .xlsx or .csv files, up to 5MB and 5,000 rows.</p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.xlsx"
            onChange={handleFileChange}
            className={styles.fileInput}
            id="transaction-file-input"
          />
          <label htmlFor="transaction-file-input" className={styles.chooseButton}>
            Choose file
          </label>
          {selectedFile && <div className={styles.fileName}>{selectedFile.name}</div>}
          <div>
            <button
              className={styles.uploadButton}
              onClick={handleUpload}
              disabled={!selectedFile}
            >
              Upload and preview
            </button>
          </div>
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
              Preview — {preview.total_row_count} row{preview.total_row_count === 1 ? "" : "s"}{" "}
              detected in {preview.filename}
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
              {STANDARD_FIELDS.map((field) => (
                <div key={field} className={styles.mappingRow}>
                  <label className={styles.mappingLabel}>
                    {FIELD_LABELS[field]}
                    {OPTIONAL_FIELDS.includes(field) && (
                      <span className={styles.mappingOptional}> (optional)</span>
                    )}
                  </label>
                  <select
                    className={styles.select}
                    value={mapping[field] ?? ""}
                    onChange={(e) => handleMappingChange(field, e.target.value)}
                  >
                    <option value="">
                      {OPTIONAL_FIELDS.includes(field) ? "-- Not in file --" : "-- Select column --"}
                    </option>
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
                {stage === "confirming" ? "Importing…" : "Confirm and import"}
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
              <div className={`${styles.resultStatValue} ${styles.successValue}`}>
                {result.imported_row_count}
              </div>
              <div className={styles.resultStatLabel}>Imported</div>
            </div>
            <div className={styles.resultStat}>
              <div className={`${styles.resultStatValue} ${styles.failValue}`}>
                {result.failed_row_count}
              </div>
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
