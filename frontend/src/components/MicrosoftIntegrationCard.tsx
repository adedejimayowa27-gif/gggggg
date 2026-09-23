"use client";

/**
 * Excel/OneDrive integration card -- same shape as GoogleIntegrationCard,
 * mirroring backend/app/api/routes/microsoft_integration.py (itself
 * deliberately parallel to google_integration.py). See that component's
 * docstring for the shared flow and role requirements; the only real
 * difference is Microsoft's vocabulary (workbook/worksheet id instead of
 * spreadsheet/worksheet title).
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import {
  connectMicrosoft,
  disconnectMicrosoft,
  getMicrosoftStatus,
  listExcelWorksheets,
  listWorkbooks,
  previewExcelWorksheet,
  runExcelSync,
  saveExcelMapping,
  saveExcelSelection,
} from "@/lib/microsoft";
import {
  STANDARD_FIELDS,
  type ColumnMapping,
  type ExcelPreview,
  type ExcelSyncResult,
  type ExcelWorksheetItem,
  type MicrosoftIntegrationStatus,
  type StandardField,
  type TeamRole,
  type WorkbookItem,
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

export default function MicrosoftIntegrationCard({ businessId, role }: Props) {
  const { token } = useAuth();
  const canManage = hasRole(role, "admin");
  const canSync = hasRole(role, "member");

  const [status, setStatus] = useState<MicrosoftIntegrationStatus | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  const [workbooks, setWorkbooks] = useState<WorkbookItem[] | null>(null);
  const [selectedWorkbookId, setSelectedWorkbookId] = useState("");
  const [worksheets, setWorksheets] = useState<ExcelWorksheetItem[] | null>(null);
  const [selectedWorksheetId, setSelectedWorksheetId] = useState("");
  const [isPickingSheet, setIsPickingSheet] = useState(false);
  const [isSavingSelection, setIsSavingSelection] = useState(false);

  const [preview, setPreview] = useState<ExcelPreview | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isSavingMapping, setIsSavingMapping] = useState(false);

  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<ExcelSyncResult | null>(null);

  const loadStatus = async () => {
    if (!token) return;
    try {
      const data = await getMicrosoftStatus(businessId, token);
      setStatus(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load Excel/OneDrive status.");
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
      const { authorization_url } = await connectMicrosoft(businessId, token);
      window.location.href = authorization_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the Microsoft connection.");
      setIsConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!token) return;
    setError(null);
    setIsDisconnecting(true);
    try {
      await disconnectMicrosoft(businessId, token);
      setStatus(null);
      setWorkbooks(null);
      setWorksheets(null);
      setPreview(null);
      setMapping(null);
      setSyncResult(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not disconnect Excel/OneDrive.");
    } finally {
      setIsDisconnecting(false);
    }
  };

  const openSheetPicker = async () => {
    if (!token) return;
    setError(null);
    setIsPickingSheet(true);
    setWorkbooks(null);
    try {
      const items = await listWorkbooks(businessId, token);
      setWorkbooks(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load workbooks.");
    }
  };

  const handleWorkbookChosen = async (workbookItemId: string) => {
    setSelectedWorkbookId(workbookItemId);
    setSelectedWorksheetId("");
    setWorksheets(null);
    if (!token || !workbookItemId) return;
    try {
      const items = await listExcelWorksheets(businessId, workbookItemId, token);
      setWorksheets(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load worksheets.");
    }
  };

  const handleSaveSelection = async () => {
    if (!token || !selectedWorkbookId || !selectedWorksheetId) return;
    setError(null);
    setIsSavingSelection(true);
    try {
      const updated = await saveExcelSelection(businessId, selectedWorkbookId, selectedWorksheetId, token);
      setStatus(updated);
      setIsPickingSheet(false);
      setWorkbooks(null);
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
      const data = await previewExcelWorksheet(businessId, token);
      setPreview(data);
      // Same Record<string, ...> vs ColumnMapping looseness as
      // GoogleIntegrationCard's identical line -- see that file's
      // comment here.
      setMapping(data.suggested_mapping as ColumnMapping);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not preview this worksheet.");
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
      const updated = await saveExcelMapping(businessId, mapping, token);
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
      const result = await runExcelSync(businessId, token);
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
        <div className={`${styles.iconWrap} ${styles.iconWrapBlue}`}>E</div>
        <div>
          <h2 className={styles.cardTitle}>Excel / OneDrive</h2>
          <p className={styles.cardDescription}>
            Keep transactions in sync with a workbook stored in OneDrive.
          </p>
        </div>
      </div>

      {status === undefined && <p className={styles.muted}>Loading…</p>}

      {status === null && canManage && (
        <button className={styles.primaryButton} onClick={handleConnect} disabled={isConnecting}>
          {isConnecting ? "Redirecting to Microsoft…" : "Connect Excel / OneDrive"}
        </button>
      )}
      {status === null && !canManage && (
        <p className={styles.muted}>Not connected. An admin can connect Excel/OneDrive.</p>
      )}

      {status && (
        <>
          <div className={styles.connectedRow}>
            <span className={styles.connectedBadge}>Connected</span>
            <span className={styles.connectedEmail}>{status.microsoft_email}</span>
            {canManage && (
              <button className={styles.linkButton} onClick={handleDisconnect} disabled={isDisconnecting}>
                {isDisconnecting ? "Disconnecting…" : "Disconnect"}
              </button>
            )}
          </div>

          {status.workbook_item_id && (
            <p className={styles.muted}>
              Syncing from <strong>{status.workbook_name}</strong> — {status.worksheet_name}
            </p>
          )}
          {status.last_sync_error && <p className={styles.error}>Last sync error: {status.last_sync_error}</p>}

          <div className={styles.linkStack}>
            {canManage && !isPickingSheet && (
              <button className={styles.linkButton} onClick={openSheetPicker}>
                {status.workbook_item_id ? "Change workbook" : "Choose a workbook"}
              </button>
            )}
            {status.workbook_item_id && !preview && (
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
              {workbooks === null && <p className={styles.muted}>Loading workbooks…</p>}
              {workbooks && (
                <label>
                  Workbook
                  <select value={selectedWorkbookId} onChange={(e) => handleWorkbookChosen(e.target.value)}>
                    <option value="">-- Select a workbook --</option>
                    {workbooks.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {worksheets && (
                <label>
                  Worksheet (tab)
                  <select value={selectedWorksheetId} onChange={(e) => setSelectedWorksheetId(e.target.value)}>
                    <option value="">-- Select a worksheet --</option>
                    {worksheets.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <div>
                <button
                  className={styles.primaryButton}
                  onClick={handleSaveSelection}
                  disabled={!selectedWorkbookId || !selectedWorksheetId || isSavingSelection}
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
