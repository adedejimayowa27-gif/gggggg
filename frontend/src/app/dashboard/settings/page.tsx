"use client";

/**
 * Settings page -- the Google Sheets and Microsoft Excel/OneDrive
 * integration setup/sync flows, plus branch management. Receives the
 * OAuth callbacks' ?google=connected/error and ?microsoft=connected/error
 * redirects.
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
import { createBranch, deleteBranch, listBranches } from "@/lib/branches";
import {
  STANDARD_FIELDS,
  type GoogleIntegrationStatus,
  type SheetPreview,
  type SpreadsheetItem,
  type StandardField,
  type SyncResult,
  type WorksheetItem,
  type Branch,
  type MicrosoftIntegrationStatus,
  type ExcelPreview,
  type ExcelSyncResult,
  type ExcelWorksheetItem,
  type WorkbookItem,
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

  // --- Microsoft Excel/OneDrive (mirrors the Google state block above
  // exactly, kept in separate state since a business can have both
  // integrations connected at once, independently) ---
  const [excelStatus, setExcelStatus] = useState<MicrosoftIntegrationStatus | null | undefined>(undefined);
  const [excelCallbackNotice, setExcelCallbackNotice] = useState<string | null>(null);

  const [workbooks, setWorkbooks] = useState<WorkbookItem[]>([]);
  const [excelWorksheets, setExcelWorksheets] = useState<ExcelWorksheetItem[]>([]);
  const [selectedWorkbook, setSelectedWorkbook] = useState("");
  const [selectedExcelWorksheet, setSelectedExcelWorksheet] = useState("");

  const [excelPreview, setExcelPreview] = useState<ExcelPreview | null>(null);
  const [excelMapping, setExcelMapping] = useState<Record<string, string | null>>({});

  const [excelSyncResult, setExcelSyncResult] = useState<ExcelSyncResult | null>(null);
  const [isExcelBusy, setIsExcelBusy] = useState(false);
  const [excelError, setExcelError] = useState<string | null>(null);

  const [branches, setBranches] = useState<Branch[]>([]);
  const [newBranchName, setNewBranchName] = useState("");
  const [branchError, setBranchError] = useState<string | null>(null);

  const loadBranches = () => {
    if (!token || !primaryBusiness) return;
    listBranches(primaryBusiness.id, token)
      .then(setBranches)
      .catch(() => undefined);
  };

  useEffect(loadBranches, [token, primaryBusiness]);

  const handleAddBranch = () => {
    if (!token || !primaryBusiness || !newBranchName.trim()) return;
    setBranchError(null);
    createBranch(primaryBusiness.id, { name: newBranchName.trim() }, token)
      .then(() => {
        setNewBranchName("");
        loadBranches();
      })
      .catch((err) => setBranchError(err instanceof ApiError ? err.message : "Could not add branch."));
  };

  const handleDeleteBranch = (branchId: string) => {
    if (!token || !primaryBusiness) return;
    deleteBranch(primaryBusiness.id, branchId, token).then(loadBranches);
  };

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

  // --- Microsoft Excel/OneDrive handlers (mirror the Google handlers
  // above exactly) ---
  const loadExcelStatus = () => {
    if (!token || !primaryBusiness) return;
    getMicrosoftStatus(primaryBusiness.id, token).then(setExcelStatus);
  };

  useEffect(loadExcelStatus, [token, primaryBusiness]);

  useEffect(() => {
    const flag = searchParams.get("microsoft");
    if (flag === "connected") setExcelCallbackNotice("Microsoft account connected successfully.");
    if (flag === "error") setExcelCallbackNotice("Could not connect your Microsoft account. Please try again.");
  }, [searchParams]);

  const handleConnectExcel = () => {
    if (!token || !primaryBusiness) return;
    setExcelError(null);
    setIsExcelBusy(true);
    connectMicrosoft(primaryBusiness.id, token)
      .then((res) => {
        window.location.href = res.authorization_url;
      })
      .catch((err) => {
        setExcelError(
          err instanceof ApiError
            ? err.message
            : "Could not start Microsoft connection. Please try again."
        );
        setIsExcelBusy(false);
      });
  };

  const handleDisconnectExcel = () => {
    if (!token || !primaryBusiness) return;
    disconnectMicrosoft(primaryBusiness.id, token).then(() => {
      setExcelStatus(null);
      setWorkbooks([]);
      setExcelWorksheets([]);
      setExcelPreview(null);
      setExcelSyncResult(null);
    });
  };

  const loadWorkbooks = () => {
    if (!token || !primaryBusiness) return;
    setIsExcelBusy(true);
    setExcelError(null);
    listWorkbooks(primaryBusiness.id, token)
      .then(setWorkbooks)
      .catch((err) => setExcelError(err instanceof ApiError ? err.message : "Could not load workbooks."))
      .finally(() => setIsExcelBusy(false));
  };

  const handlePickWorkbook = (id: string) => {
    setSelectedWorkbook(id);
    setSelectedExcelWorksheet("");
    if (!token || !primaryBusiness || !id) return;
    listExcelWorksheets(primaryBusiness.id, id, token).then(setExcelWorksheets);
  };

  const handleSaveExcelSelection = () => {
    if (!token || !primaryBusiness || !selectedWorkbook || !selectedExcelWorksheet) return;
    setIsExcelBusy(true);
    setExcelError(null);
    saveExcelSelection(primaryBusiness.id, selectedWorkbook, selectedExcelWorksheet, token)
      .then((updated) => {
        setExcelStatus(updated);
        return previewExcelWorksheet(primaryBusiness.id, token);
      })
      .then((p) => {
        setExcelPreview(p);
        setExcelMapping(p.suggested_mapping);
      })
      .catch((err) => setExcelError(err instanceof ApiError ? err.message : "Could not save selection."))
      .finally(() => setIsExcelBusy(false));
  };

  const handleSaveExcelMapping = () => {
    if (!token || !primaryBusiness) return;
    setIsExcelBusy(true);
    setExcelError(null);
    saveExcelMapping(primaryBusiness.id, excelMapping, token)
      .then(setExcelStatus)
      .catch((err) => setExcelError(err instanceof ApiError ? err.message : "Could not save mapping."))
      .finally(() => setIsExcelBusy(false));
  };

  const handleExcelSync = () => {
    if (!token || !primaryBusiness) return;
    setIsExcelBusy(true);
    setExcelError(null);
    setExcelSyncResult(null);
    runExcelSync(primaryBusiness.id, token)
      .then((result) => {
        setExcelSyncResult(result);
        loadExcelStatus();
      })
      .catch((err) => setExcelError(err instanceof ApiError ? err.message : "Sync failed."))
      .finally(() => setIsExcelBusy(false));
  };

  if (isLoadingBusinesses || status === undefined || excelStatus === undefined) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness || !token) {
    return <ComingSoon title="Settings" description="Create a business to manage settings here." />;
  }

  const requiredFieldsMapped = STANDARD_FIELDS.filter((f) => !OPTIONAL_FIELDS.includes(f)).every(
    (f) => mapping[f]
  );
  const excelRequiredFieldsMapped = STANDARD_FIELDS.filter((f) => !OPTIONAL_FIELDS.includes(f)).every(
    (f) => excelMapping[f]
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

      <div className={styles.card}>
        <h2>Microsoft Excel Integration</h2>

        {excelCallbackNotice && <p className={styles.notice}>{excelCallbackNotice}</p>}

        {!excelStatus && (
          <>
            <p className={styles.muted}>
              Connect a Microsoft account to import transactions directly from an Excel workbook
              stored in OneDrive.
            </p>
            <button className={styles.primaryButton} onClick={handleConnectExcel} disabled={isExcelBusy}>
              {isExcelBusy ? "Connecting…" : "Connect Microsoft Account"}
            </button>
          </>
        )}

        {excelStatus && (
          <>
            <p className={styles.connectedRow}>
              Connected as <strong>{excelStatus.microsoft_email}</strong>
              {excelStatus.status === "error" && (
                <span className={styles.errorBadge}>Reconnect needed</span>
              )}
              <button className={styles.linkButton} onClick={handleDisconnectExcel}>
                Disconnect
              </button>
            </p>

            {!workbooks.length && (
              <button className={styles.primaryButton} onClick={loadWorkbooks} disabled={isExcelBusy}>
                {isExcelBusy ? "Loading…" : "Choose a workbook"}
              </button>
            )}

            {workbooks.length > 0 && (
              <div className={styles.formRow}>
                <label>
                  Workbook
                  <select value={selectedWorkbook} onChange={(e) => handlePickWorkbook(e.target.value)}>
                    <option value="">-- Select --</option>
                    {workbooks.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                </label>

                {excelWorksheets.length > 0 && (
                  <label>
                    Worksheet
                    <select
                      value={selectedExcelWorksheet}
                      onChange={(e) => setSelectedExcelWorksheet(e.target.value)}
                    >
                      <option value="">-- Select --</option>
                      {excelWorksheets.map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                {selectedWorkbook && selectedExcelWorksheet && (
                  <button
                    className={styles.primaryButton}
                    onClick={handleSaveExcelSelection}
                    disabled={isExcelBusy}
                  >
                    Use this worksheet
                  </button>
                )}
              </div>
            )}

            {excelStatus.workbook_name && !excelPreview && (
              <p className={styles.muted}>
                Currently using <strong>{excelStatus.workbook_name}</strong> / {excelStatus.worksheet_name}
                {excelStatus.has_confirmed_mapping ? " -- mapping already saved." : ""}
              </p>
            )}

            {excelPreview && (
              <div className={styles.mappingBlock}>
                <h3>Map columns</h3>
                <p className={styles.muted}>{excelPreview.total_row_count} rows detected in this worksheet.</p>
                {STANDARD_FIELDS.map((field) => (
                  <div key={field} className={styles.mappingRow}>
                    <label>
                      {FIELD_LABELS[field]}
                      {OPTIONAL_FIELDS.includes(field) && <span className={styles.muted}> (optional)</span>}
                    </label>
                    <select
                      value={excelMapping[field] ?? ""}
                      onChange={(e) =>
                        setExcelMapping((prev) => ({ ...prev, [field]: e.target.value || null }))
                      }
                    >
                      <option value="">
                        {OPTIONAL_FIELDS.includes(field) ? "-- Not in workbook --" : "-- Select column --"}
                      </option>
                      {excelPreview.detected_columns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
                <button
                  className={styles.primaryButton}
                  onClick={handleSaveExcelMapping}
                  disabled={isExcelBusy || !excelRequiredFieldsMapped}
                >
                  Save mapping
                </button>
              </div>
            )}

            {excelStatus.has_confirmed_mapping && (
              <div className={styles.syncBlock}>
                <p className={styles.muted}>
                  {excelStatus.last_synced_at
                    ? `Last synced: ${new Date(excelStatus.last_synced_at).toLocaleString()}`
                    : "Never synced yet."}
                </p>
                {excelStatus.last_sync_error && (
                  <p className={styles.error}>Last error: {excelStatus.last_sync_error}</p>
                )}
                <button className={styles.primaryButton} onClick={handleExcelSync} disabled={isExcelBusy}>
                  {isExcelBusy ? "Syncing…" : "Sync Now"}
                </button>
              </div>
            )}

            {excelSyncResult && (
              <div className={styles.syncResult}>
                <p>
                  Imported <strong>{excelSyncResult.imported_row_count}</strong>, skipped{" "}
                  <strong>{excelSyncResult.skipped_duplicate_count}</strong> duplicate
                  {excelSyncResult.skipped_duplicate_count === 1 ? "" : "s"}, failed{" "}
                  <strong>{excelSyncResult.failed_row_count}</strong> out of{" "}
                  {excelSyncResult.total_row_count} rows.
                </p>
                {excelSyncResult.row_errors.length > 0 && (
                  <ul className={styles.rowErrors}>
                    {excelSyncResult.row_errors.slice(0, 5).map((e) => (
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

        {excelError && <p className={styles.error}>{excelError}</p>}
      </div>

      <div className={styles.card}>
        <h2>Branches</h2>
        <p className={styles.muted}>
          Optional -- organize this business&apos;s activity by location if it has more than one.
        </p>

        {branches.length === 0 && <p className={styles.muted}>No branches yet.</p>}
        <ul className={styles.savedList}>
          {branches.map((b) => (
            <li key={b.id} className={styles.branchRow}>
              <span>
                {b.name}
                {b.is_default && <span className={styles.defaultTag}> (default)</span>}
              </span>
              <button className={styles.linkButton} onClick={() => handleDeleteBranch(b.id)}>
                Remove
              </button>
            </li>
          ))}
        </ul>

        <div className={styles.formRow}>
          <input
            type="text"
            placeholder="New branch name"
            value={newBranchName}
            onChange={(e) => setNewBranchName(e.target.value)}
          />
          <button className={styles.primaryButton} onClick={handleAddBranch}>
            Add branch
          </button>
        </div>
        {branchError && <p className={styles.error}>{branchError}</p>}
      </div>
    </div>
  );
}
