"use client";

/**
 * Inventory settings card for the Settings page (Step 13, Batch 3):
 * the single toggle for Business.auto_deduct_stock_on_sale -- whether
 * creating/editing/deleting a transaction automatically adjusts a
 * matching stock record. "admin"+ only, matching billing/integration
 * setup elsewhere on this page.
 */
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { ApiError } from "@/lib/api";
import { updateBusiness } from "@/lib/business";
import { hasRole } from "@/lib/permissions";
import type { Business, TeamRole } from "@/types";
import styles from "@/app/dashboard/settings/settings.module.css";
import toggleStyles from "./InventorySettingsCard.module.css";

interface Props {
  business: Business;
  role: TeamRole | null;
}

export default function InventorySettingsCard({ business, role }: Props) {
  const { token } = useAuth();
  const { refreshBusinesses } = useDashboard();
  const canEdit = hasRole(role, "admin");

  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleToggle = async () => {
    if (!token || isSaving || !canEdit) return;
    setIsSaving(true);
    setError(null);
    try {
      await updateBusiness(business.id, { auto_deduct_stock_on_sale: !business.auto_deduct_stock_on_sale }, token);
      await refreshBusinesses();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update this setting.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={styles.card}>
      <h2 className={styles.cardTitle}>Inventory</h2>
      <p className={styles.cardDescription}>
        Track stock on the Stock page. Turn this on to have a sale automatically reduce a matching product&apos;s
        stock -- editing or deleting that sale later adjusts it back correctly.
      </p>

      <label className={toggleStyles.toggleRow}>
        <span>
          <span className={toggleStyles.toggleLabel}>Deduct stock automatically on sale</span>
          {!canEdit && <span className={toggleStyles.toggleHint}>Only an admin can change this.</span>}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={business.auto_deduct_stock_on_sale}
          className={`${toggleStyles.switch} ${business.auto_deduct_stock_on_sale ? toggleStyles.switchOn : ""}`}
          onClick={handleToggle}
          disabled={!canEdit || isSaving}
        >
          <span className={toggleStyles.knob} />
        </button>
      </label>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
