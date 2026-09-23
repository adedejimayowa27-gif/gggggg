"use client";

/**
 * Google Sheets integration card, for the Settings page.
 *
 * Flow mirrors backend/app/api/routes/google_integration.py exactly:
 * connect (redirect to Google) -> callback lands back on this page with
 * ?google=connected|error (read by the parent page, not here) -> pick a
 * spreadsheet + worksheet -> preview + confirm a column mapping (same
 * StandardField concept as the CSV importer -- see
 * TransactionImportWizard.tsx) -> Sync Now.
 *
 * Every write action (connect, disconnect, selection, mapping) requires
 * "admin"+; Sync Now only requires "member"+ -- see permissions.ts and
 * this route file's require_business_role calls. Buttons are hidden
 * rather than disabled for a role that can't use them, same convention
 * as team/page.tsx.
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
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
  type ColumnMapping,
  type GoogleIntegrationStatus,
  type SheetPreview,
  type SpreadsheetItem,
  type StandardField,
  type SyncResult,
  type TeamRole,
  type WorksheetItem,
} from "@/types";
import { hasRole } from "@/lib/permissions";
import styles from "@/app/dashboard/settings/settings.module.css";

const FIELD_LABELS: Record<StandardField, string> = {
  date: "Date",
  product: "Product",
  quantity: "Quantity",
  selling_price: "Selling Price",
  cost_price: "Cost Price",
  category: "Category",
  customer: "Customer",
  payment_method: "Payment Method",
  branch: "Branch",
};

const OPTIONAL_FIELDS: StandardField[] = [
  "cost_price",
  "category",
  "customer",
  "payment_method",
  "branch",
];

interface Props {
  businessId: string;
  role: TeamRole | null;
}

export default function GoogleIntegrationCard({ businessId, role }: Props) {
  const { token } = useAuth();
  const canManage = hasRole(role, "admin");
  const canSync = hasRole(role, "member");

  const [status, setStatus] = useState<GoogleIntegrationStatus | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  const [spreadsheets, setSpreadsheets] = useState<SpreadsheetItem[] | null>(null);
  const [selectedSpreadsheetId, setSelectedSpreadsheetId] = useState("");
  const [worksheets, setWorksheets] = useState<WorksheetItem[] | null>(null);
  const [selectedWorksheetTitle, setSelectedWorksheetTitle] = useState("");
  const [isPickingSheet, setIsPickingSheet] = useState(false);
  const [isSavingSelection, setIsSavingSelection] = useState(false);

  const [preview, setPreview] = useState<SheetPreview | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isSavingMapping, setIsSavingMapping] = useState(false);

  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);

  const loadStatus = async () => {
    if (!token) return;
    try {
      const data = await getGoogleStatus(businessId, token);
      setStatus(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load Google Sheets status.");
      setStatus(null);
    }
  };

  useEffect(() => {
    loadStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId, token]);

  const handleConnect = async () => {
    if (!token) return;
    setError(null);
    setIsConnecting(true);
    try {
      const { authorization_url } = await connectGoogle(businessId, token);
      window.location.href = authorization_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start Google connection.");
      setIsConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!token) return;
    setError(null);
    setIsDisconnecting(true);
    try {
      await disconnectGoogle(businessId, token);
      setStatus(null);
      setSpreadsheets(null);
      setWorksheets(null);
      setPreview(null);
      setMapping(null);
      setSyncResult(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not disconnect Google Sheets.");
    } finally {
      setIsDisconnecting(false);
    }
  };

  const openSheetPicker = async () => {
    if (!token) return;
    setError(null);
    setIsPickingSheet(true);
    setSpreadsheets(null);
    try {
      const items = await listSpreadsheets(businessId, token);
      setSpreadsheets(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load spreadsheets.");
    }
  };

  const handleSpreadsheetChosen = async (spreadsheetId: string) => {
    setSelectedSpreadsheetId(spreadsheetId);
    setSelectedWorksheetTitle("");
    setWorksheets(null);
    if (!token || !spreadsheetId) return;
    try {
      const items = await listWorksheets(businessId, spreadsheetId, token);
      setWorksheets(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load worksheets.");
    }
  };

  const handleSaveSelection = async () => {
    if (!token || !selectedSpreadsheetId || !selectedWorksheetTitle) return;
    setError(null);
    setIsSavingSelection(true);
    try {
      const updated = await saveSelection(businessId, selectedSpreadsheetId, selectedWorksheetTitle, token);
      setStatus(updated);
      setIsPickingSheet(false);
      setSpreadsheets(null);
      setWorksheets(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your selection.");
    } finally {
      setIsSavingSelection(false);
    }
  };

  const handleLoadPreview = async () => {
    if (!token) return;
    setError(null);
    setIsLoadingPreview(true);
    setSyncResult(null);
    try {
      const data = await previewSheet(businessId, token);
      setPreview(data);
      // suggested_mapping on SheetPreview is typed as the looser
      // Record<string, string | null> (unlike CSV import's
      // ImportPreview, which is typed as ColumnMapping directly) --
      // the backend (services/sheets_sync.py) always builds it from
      // the same StandardField keys, so this cast just matches what's
      // actually there.
      setMapping(data.suggested_mapping as ColumnMapping);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not preview this sheet.");
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const handleMappingChange = (field: StandardField, column: string) => {
    setMapping((prev) => (prev ? { ...prev, [field]: column || null } : prev));
  };

  const handleSaveMapping = async () => {
    if (!token || !mapping) return;
    setError(null);
    setIsSavingMapping(true);
    try {
      const updated = await saveMapping(businessId, mapping, token);
      setStatus(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the column mapping.");
    } finally {
      setIsSavingMapping(false);
    }
  };

  const handleSync = async () => {
    if (!token) return;
    setError(null);
    setIsSyncing(true);
    setSyncResult(null);
    try {
      const result = await runSync(businessId, token);
      setSyncResult(result);
      await loadStatus();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sync failed. Please try again.");
    } finally {
      setIsSyncing(false);
    }
  };

  const requiredFieldsMapped =
    mapping && STANDARD_FIELDS.filter((f) => !OPTIONAL_FIELDS.includes(f)).every((f) => mapping[f]);

  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <div className={`${styles.iconWrap} ${styles.iconWrapLeaf}`}>G</div>
        <div>
          <h2 className={styles.cardTitle}>Google Sheets</h2>
          <p className={styles.cardDescription}>
            Keep transactions in sync with a spreadsheet instead of uploading files by hand.
          </p>
        </div>
      </div>

      {status === undefined && <p className={styles.muted}>Loading…</p>}

      {status === null && canManage && (
        <button className={styles.primaryButton} onClick={handleConnect} disabled={isConnecting}>
          {isConnecting ? "Redirecting to Google…" : "Connect Google Sheets"}
        </button>
      )}
      {status === null && !canManage && (
        <p className={styles.muted}>Not connected. An admin can connect Google Sheets.</p>
      )}

      {status && (
        <>
          <div className={styles.connectedRow}>
            <span className={styles.connectedBadge}>Connected</span>
            <span className={styles.connectedEmail}>{status.google_email}</span>
            {canManage && (
              <button className={styles.linkButton} onClick={handleDisconnect} disabled={isDisconnecting}>
                {isDisconnecting ? "Disconnecting…" : "Disconnect"}
              </button>
            )}
          </div>

          {status.spreadsheet_id && (
            <p className={styles.muted}>
              Syncing from <strong>{status.spreadsheet_name}</strong> — {status.worksheet_title}
            </p>
          )}
          {status.last_sync_error && <p className={styles.error}>Last sync error: {status.last_sync_error}</p>}

          <div className={styles.linkStack}>
            {canManage && !isPickingSheet && (
              <button className={styles.linkButton} onClick={openSheetPicker}>
                {status.spreadsheet_id ? "Change spreadsheet" : "Choose a spreadsheet"}
              </button>
            )}
            {status.spreadsheet_id && !preview && (
              <button className={styles.linkButton} onClick={handleLoadPreview} disabled={isLoadingPreview}>
                {isLoadingPreview
                  ? "Loading preview…"
                  : status.has_confirmed_mapping
                  ? "Review column mapping"
                  : "Preview and map columns"}
              </button>
            )}
          </div>

          {canManage && isPickingSheet && (
            <div className={styles.formRow}>
              {spreadsheets === null && <p className={styles.muted}>Loading spreadsheets…</p>}
              {spreadsheets && (
                <label>
                  Spreadsheet
                  <select
                    value={selectedSpreadsheetId}
                    onChange={(e) => handleSpreadsheetChosen(e.target.value)}
                  >
                    <option value="">-- Select a spreadsheet --</option>
                    {spreadsheets.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {worksheets && (
                <label>
                  Worksheet (tab)
                  <select
                    value={selectedWorksheetTitle}
                    onChange={(e) => setSelectedWorksheetTitle(e.target.value)}
                  >
                    <option value="">-- Select a worksheet --</option>
                    {worksheets.map((w) => (
                      <option key={w.title} value={w.title}>
                        {w.title}
                      </option>
                    ))}
                  </select>
                </label>
              )}


              <div>
                <button
                  className={styles.primaryButton}
                  onClick={handleSaveSelection}
                  disabled={!selectedSpreadsheetId || !selectedWorksheetTitle || isSavingSelection}
                >
                  {isSavingSelection ? "Saving…" : "Save selection"}
                </button>
                <button className={styles.linkButton} onClick={() => setIsPickingSheet(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}


          {preview && mapping && (
            <div className={styles.mappingBlock}>
              <h3>Map your columns — {preview.total_row_count} rows detected</h3>
              {STANDARD_FIELDS.map((field) => (
                <div key={field} className={styles.mappingRow}>
                  <label>
                    {FIELD_LABELS[field]}
                    {OPTIONAL_FIELDS.includes(field) && " (optional)"}
                  </label>
                  <select value={mapping[field] ?? ""} onChange={(e) => handleMappingChange(field, e.target.value)}>
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
              <div>
                <button
                  className={styles.primaryButton}
                  onClick={handleSaveMapping}
                  disabled={!requiredFieldsMapped || isSavingMapping}
                >
                  {isSavingMapping ? "Saving…" : "Save mapping"}
                </button>
                <button className={styles.linkButton} onClick={() => setPreview(null)}>
                  Close
                </button>
              </div>
            </div>
          )}

          {status.has_confirmed_mapping && canSync && (
            <div className={styles.syncBlock}>
              <button className={styles.primaryButton} onClick={handleSync} disabled={isSyncing}>
                {isSyncing ? "Syncing…" : "Sync now"}
              </button>
              {status.last_synced_at && (
                <span className={styles.muted}> Last synced {new Date(status.last_synced_at).toLocaleString()}</span>
              )}
            </div>
          )}

          {syncResult && (
            <div className={styles.syncResult}>
              <p>
                Imported {syncResult.imported_row_count} row{syncResult.imported_row_count === 1 ? "" : "s"}
                {syncResult.skipped_duplicate_count > 0 &&
                  `, skipped ${syncResult.skipped_duplicate_count} already-imported`}
                {syncResult.failed_row_count > 0 && `, ${syncResult.failed_row_count} failed`}.
              </p>
              {syncResult.row_errors.length > 0 && (
                <ul className={styles.rowErrors}>
                  {syncResult.row_errors.map((rowError) => (
                    <li key={rowError.row_number}>
                      Row {rowError.row_number}: {rowError.errors.join(" ")}
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
  );
}
