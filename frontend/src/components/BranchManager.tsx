"use client";

/**
 * Branch management card for the Settings page. Mirrors
 * backend/app/api/routes/branches.py: create/edit is "member"+,
 * delete is "admin"+ (see permissions.ts's role table) -- the delete
 * button uses the same "click again to confirm" pattern as
 * team/page.tsx's member removal, for one consistent destructive-action
 * pattern app-wide.
 */
import { FormEvent, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { createBranch, deleteBranch, listBranches, updateBranch } from "@/lib/branches";
import { hasRole } from "@/lib/permissions";
import type { Branch, TeamRole } from "@/types";
import styles from "@/app/dashboard/settings/settings.module.css";

interface Props {
  businessId: string;
  role: TeamRole | null;
}

export default function BranchManager({ businessId, role }: Props) {
  const { token } = useAuth();
  const canEdit = hasRole(role, "member");
  const canDelete = hasRole(role, "admin");

  const [branches, setBranches] = useState<Branch[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);

  const load = async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const data = await listBranches(businessId, token);
      setBranches(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load branches.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId, token]);

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (!token || !name.trim()) return;
    setError(null);
    setIsCreating(true);
    try {
      await createBranch(businessId, { name: name.trim(), address: address.trim() || undefined }, token);
      setName("");
      setAddress("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the branch.");
    } finally {
      setIsCreating(false);
    }
  };

  const handleSetDefault = async (branch: Branch) => {
    if (!token || branch.is_default) return;
    setError(null);
    try {
      await updateBranch(businessId, branch.id, { is_default: true }, token);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not set the default branch.");
    }
  };

  const handleDeleteClick = (branchId: string) => {
    if (confirmingDeleteId === branchId) {
      handleDelete(branchId);
    } else {
      setConfirmingDeleteId(branchId);
    }
  };

  const handleDelete = async (branchId: string) => {
    if (!token) return;
    setError(null);
    try {
      await deleteBranch(businessId, branchId, token);
      setConfirmingDeleteId(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete this branch.");
      setConfirmingDeleteId(null);
    }
  };

  return (
    <div className={styles.card}>
      <h2 className={styles.cardTitle}>Branches</h2>
      <p className={styles.cardDescription}>
        Locations transactions can be attributed to. The default branch is used when a transaction
        doesn&apos;t specify one.
      </p>

      {isLoading && <p className={styles.muted}>Loading…</p>}

      {!isLoading && branches.length === 0 && <p className={styles.muted}>No branches yet.</p>}

      {branches.map((branch) => (
        <div key={branch.id} className={styles.branchRow}>
          <div>
            <strong>{branch.name}</strong>
            {branch.is_default && <span className={styles.defaultTag}>Default</span>}
            {branch.address && <div className={styles.muted}>{branch.address}</div>}
          </div>
          <div>
            {canEdit && !branch.is_default && (
              <button className={styles.linkButton} onClick={() => handleSetDefault(branch)}>
                Set as default
              </button>
            )}
            {canDelete && (
              <button
                className={confirmingDeleteId === branch.id ? styles.removeButtonConfirm : styles.removeButton}
                onClick={() => handleDeleteClick(branch.id)}
              >
                {confirmingDeleteId === branch.id ? "Click again to delete" : "Delete"}
              </button>
            )}
          </div>
        </div>
      ))}

      {canEdit && (
        <form className={styles.formRow} onSubmit={handleCreate}>
          <label>Add a branch</label>
          <input
            type="text"
            placeholder="Branch name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <input
            type="text"
            placeholder="Address (optional)"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
          <button className={styles.primaryButton} type="submit" disabled={isCreating || !name.trim()}>
            {isCreating ? "Adding…" : "Add branch"}
          </button>
        </form>
      )}

      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
