"use client";

/**
 * Load / remove buttons for the onboarding sample data (Step 13,
 * Batch 4). Shared by the getting-started checklist and the Settings
 * page so both behave identically.
 *
 * After a successful load or removal the page is reloaded: sample data
 * touches almost every widget (summary cards, charts, alerts, stock,
 * the AI brief), and a one-off onboarding action isn't worth wiring a
 * refresh signal through all of them.
 */
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { loadSampleData, removeSampleData } from "@/lib/onboarding";
import styles from "./SampleDataControls.module.css";

interface Props {
  businessId: string;
  hasSampleData: boolean;
  /** Only an admin can load or remove sample data. */
  canManage: boolean;
}

export default function SampleDataControls({ businessId, hasSampleData, canManage }: Props) {
  const { token } = useAuth();
  const [isWorking, setIsWorking] = useState(false);
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canManage) return null;

  const run = async (action: () => Promise<unknown>, fallback: string) => {
    if (!token || isWorking) return;
    setIsWorking(true);
    setError(null);
    try {
      await action();
      window.location.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : fallback);
      setIsWorking(false);
    }
  };

  return (
    <div className={styles.wrap}>
      {!hasSampleData && (
        <button
          type="button"
          className={styles.primary}
          disabled={isWorking}
          onClick={() => run(() => loadSampleData(businessId, token!), "Could not load sample data.")}
        >
          {isWorking ? "Loading sample data…" : "Load sample data"}
        </button>
      )}

      {hasSampleData && !confirmingRemove && (
        <button type="button" className={styles.secondary} onClick={() => setConfirmingRemove(true)}>
          Remove sample data
        </button>
      )}

      {hasSampleData && confirmingRemove && (
        <span className={styles.confirm}>
          <span className={styles.confirmText}>Remove all sample data? Your own data isn&apos;t touched.</span>
          <button
            type="button"
            className={styles.danger}
            disabled={isWorking}
            onClick={() => run(() => removeSampleData(businessId, token!), "Could not remove sample data.")}
          >
            {isWorking ? "Removing…" : "Yes, remove it"}
          </button>
          <button type="button" className={styles.secondary} disabled={isWorking} onClick={() => setConfirmingRemove(false)}>
            Cancel
          </button>
        </span>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
