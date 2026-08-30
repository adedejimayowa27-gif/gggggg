"use client";

/**
 * Settings page (Step 9) -- currently just the Google Sheets integration
 * setup/sync flow, since that's the only setting the backend supports so
 * far. Receives the OAuth callback's ?google=connected/error redirect.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { ApiError } from "@/lib/api";
import {
  connectGoogle,
  disconnectGoogle,
  getGoogleStatus,
  listSpreadsheets,
  listWorksheets,
  previewSheet,
  runSync,
  saveMapping,
  saveSelection,
} from "@/lib/google";
import {
  STANDARD_FIELDS,
  type GoogleIntegrationStatus,
  type SheetPreview,
  type SpreadsheetItem,
  type StandardField,
  type SyncResult,
  type WorksheetItem,
} from "@/types";
import ComingSoon from "@/components/ComingSoon";
import styles from "./settings.module.css";

const FIELD_LABELS: Record<StandardField, string> = {
  date: "Date",
  product: "Product",
  quantity: "Quantity",
  selling_price: "Selling Price",
  cost_price: "Cost Price",
  category: "Category",
  customer: "Customer",
  payment_method: "Payment Method",
};
const OPTIONAL_FIELDS: StandardField[] = ["cost_price", "category", "customer", "payment_method"];

export default function SettingsPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();
  const searchParams = useSearchParams();

  const [status, setStatus] = useState<GoogleIntegrationStatus | null | undefined>(undefined);
  const [callbackNotice, setCallbackNotice] = useState<string | null>(null);

  const [spreadsheets, setSpreadsheets] = useState<SpreadsheetItem[]>([]);
  const [worksheets, setWorksheets] = useState<WorksheetItem[]>([]);
  const [selectedSpreadsheet, setSelectedSpreadsheet] = useState("");
  const [selectedWorksheet, setSelectedWorksheet] = useState("");

  const [preview, setPreview] = useState<SheetPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});

  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = () => {
    if (!token || !primaryBusiness) return;
    getGoogleStatus(primaryBusiness.id, token).then(setStatus);
  };

  useEffect(loadStatus, [token, primaryBusiness]);

  useEffect(() => {
    const flag = searchParams.get("google");
    if (flag === "connected") setCallbackNotice("Google account connected successfully.");
    if (flag === "error") setCallbackNotice("Could not connect your Google account. Please try again.");
  }, [searchParams]);

  const handleConnect = () => {
    if (!token || !primaryBusiness) return;
    setError(null);
    setIsBusy(true);
    connectGoogle(primaryBusiness.id, token)
      .then((res) => {
        window.location.href = res.authorization_url;
      })
      .catch((err) => {
        setError(
          err instanceof ApiError
            ? err.message
            : "Could not start Google connection. Please try again."
        );
        setIsBusy(false);
      });
  };

  const handleDisconnect = () => {
    if (!token || !primaryBusiness) return;
    disconnectGoogle(primaryBusiness.id, token).then(() => {
      setStatus(null);
      setSpreadsheets([]);
      setWorksheets([]);
      setPreview(null);
      setSyncResult(null);
    });
  };

  const loadSpreadsheets = () => {
    if (!token || !primaryBusiness) return;
    setIsBusy(true);
    setError(null);
    listSpreadsheets(primaryBusiness.id, token)
      .then(setSpreadsheets)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load spreadsheets."))
      .finally(() => setIsBusy(false));
  };

  const handlePickSpreadsheet = (id: string) => {
    setSelectedSpreadsheet(id);
    setSelectedWorksheet("");
    if (!token || !primaryBusiness || !id) return;
    listWorksheets(primaryBusiness.id, id, token).then(setWorksheets);
  };

  const handleSaveSelection = () => {
    if (!token || !primaryBusiness || !selectedSpreadsheet || !selectedWorksheet) return;
    setIsBusy(true);
    setError(null);
    saveSelection(primaryBusiness.id, selectedSpreadsheet, selectedWorksheet, token)
      .then((updated) => {
        setStatus(updated);
        return previewSheet(primaryBusiness.id, token);
      })
      .then((p) => {
        setPreview(p);
        setMapping(p.suggested_mapping);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not save selection."))
      .finally(() => setIsBusy(false));
  };

  const handleSaveMapping = () => {
    if (!token || !primaryBusiness) return;
    setIsBusy(true);
    setError(null);
    saveMapping(primaryBusiness.id, mapping, token)
      .then(setStatus)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not save mapping."))
      .finally(() => setIsBusy(false));
  };

  const handleSync = () => {
    if (!token || !primaryBusiness) return;
    setIsBusy(true);
    setError(null);
    setSyncResult(null);
    runSync(primaryBusiness.id, token)
      .then((result) => {
        setSyncResult(result);
        loadStatus();
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Sync failed."))
      .finally(() => setIsBusy(false));
  };

  if (isLoadingBusinesses || status === undefined) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness || !token) {
    return <ComingSoon title="Settings" description="Create a business to manage settings here." />;
  }

  const requiredFieldsMapped = STANDARD_FIELDS.filter((f) => !OPTIONAL_FIELDS.includes(f)).every(
    (f) => mapping[f]
  );

  return (
    <div>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1.5rem" }}>Settings</h1>

      {callbackNotice && <p className={styles.notice}>{callbackNotice}</p>}

      <div className={styles.card}>
        <h2>Google Sheets Integration</h2>

        {!status && (
          <>
            <p className={styles.muted}>
              Connect a Google account to import transactions directly from a spreadsheet.
            </p>
            <button className={styles.primaryButton} onClick={handleConnect} disabled={isBusy}>
              {isBusy ? "Connecting…" : "Connect Google Account"}
            </button>
          </>
        )}

        {status && (
          <>
            <p className={styles.connectedRow}>
              Connected as <strong>{status.google_email}</strong>
              {status.status === "error" && (
                <span className={styles.errorBadge}>Reconnect needed</span>
              )}
              <button className={styles.linkButton} onClick={handleDisconnect}>
                Disconnect
              </button>
            </p>

            {!spreadsheets.length && (
              <button className={styles.primaryButton} onClick={loadSpreadsheets} disabled={isBusy}>
                {isBusy ? "Loading…" : "Choose a spreadsheet"}
              </button>
            )}

            {spreadsheets.length > 0 && (
              <div className={styles.formRow}>
                <label>
                  Spreadsheet
                  <select value={selectedSpreadsheet} onChange={(e) => handlePickSpreadsheet(e.target.value)}>
                    <option value="">-- Select --</option>
                    {spreadsheets.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </label>

                {worksheets.length > 0 && (
                  <label>
                    Worksheet
                    <select value={selectedWorksheet} onChange={(e) => setSelectedWorksheet(e.target.value)}>
                      <option value="">-- Select --</option>
                      {worksheets.map((w) => (
                        <option key={w.title} value={w.title}>
                          {w.title}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                {selectedSpreadsheet && selectedWorksheet && (
                  <button className={styles.primaryButton} onClick={handleSaveSelection} disabled={isBusy}>
                    Use this sheet
                  </button>
                )}
              </div>
            )}

            {status.spreadsheet_name && !preview && (
              <p className={styles.muted}>
                Currently using <strong>{status.spreadsheet_name}</strong> / {status.worksheet_title}
                {status.has_confirmed_mapping ? " -- mapping already saved." : ""}
              </p>
            )}

            {preview && (
              <div className={styles.mappingBlock}>
                <h3>Map columns</h3>
                <p className={styles.muted}>{preview.total_row_count} rows detected in this worksheet.</p>
                {STANDARD_FIELDS.map((field) => (
                  <div key={field} className={styles.mappingRow}>
                    <label>
                      {FIELD_LABELS[field]}
                      {OPTIONAL_FIELDS.includes(field) && <span className={styles.muted}> (optional)</span>}
                    </label>
                    <select
                      value={mapping[field] ?? ""}
                      onChange={(e) =>
                        setMapping((prev) => ({ ...prev, [field]: e.target.value || null }))
                      }
                    >
                      <option value="">
                        {OPTIONAL_FIELDS.includes(field) ? "-- Not in sheet --" : "-- Select column --"}
                      </option>
                      {preview.detected_columns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
                <button
                  className={styles.primaryButton}
                  onClick={handleSaveMapping}
                  disabled={isBusy || !requiredFieldsMapped}
                >
                  Save mapping
                </button>
              </div>
            )}

            {status.has_confirmed_mapping && (
              <div className={styles.syncBlock}>
                <p className={styles.muted}>
                  {status.last_synced_at
                    ? `Last synced: ${new Date(status.last_synced_at).toLocaleString()}`
                    : "Never synced yet."}
                </p>
                {status.last_sync_error && <p className={styles.error}>Last error: {status.last_sync_error}</p>}
                <button className={styles.primaryButton} onClick={handleSync} disabled={isBusy}>
                  {isBusy ? "Syncing…" : "Sync Now"}
                </button>
              </div>
            )}

            {syncResult && (
              <div className={styles.syncResult}>
                <p>
                  Imported <strong>{syncResult.imported_row_count}</strong>, skipped{" "}
                  <strong>{syncResult.skipped_duplicate_count}</strong> duplicate
                  {syncResult.skipped_duplicate_count === 1 ? "" : "s"}, failed{" "}
                  <strong>{syncResult.failed_row_count}</strong> out of {syncResult.total_row_count} rows.
                </p>
                {syncResult.row_errors.length > 0 && (
                  <ul className={styles.rowErrors}>
                    {syncResult.row_errors.slice(0, 5).map((e) => (
                      <li key={e.row_number}>
                        Row {e.row_number}: {e.errors.join(", ")}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </>
        )}

        {error && <p className={styles.error}>{error}</p>}
      </div>
    </div>
  );
}
