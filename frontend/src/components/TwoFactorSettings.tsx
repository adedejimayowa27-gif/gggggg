"use client";

/**
 * Two-factor authentication settings -- Step 12, Batch 12.6. Lives on
 * the Account page (account-scoped, like export/delete -- see that
 * page's docstring), not Settings (business-scoped).
 *
 * Three states, driven by user.is_2fa_enabled plus local UI state:
 * 1. Off, idle -- just an "Enable" button.
 * 2. Enrolling -- setupTwoFactor() was called; showing the QR/secret
 *    and waiting for a code to confirm via enableTwoFactor().
 * 3. On, idle -- showing "Regenerate recovery codes" / "Disable",
 *    each of which opens its own password+code confirm form (using the
 *    shared style as the account-deletion form on this same page).
 *
 * Recovery codes are shown in a 4th, transient state right after
 * enabling or regenerating -- see recoveryCodes below -- since the
 * backend never returns them again after that one response.
 */
import { FormEvent, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { disableTwoFactor, enableTwoFactor, regenerateRecoveryCodes, setupTwoFactor } from "@/lib/twoFactor";
import type { TwoFactorSetup } from "@/types";
import styles from "@/app/dashboard/account/account.module.css";

type ConfirmAction = "disable" | "regenerate" | null;

export default function TwoFactorSettings() {
  const { user, token, refreshUser } = useAuth();

  const [setup, setSetup] = useState<TwoFactorSetup | null>(null);
  const [isStartingSetup, setIsStartingSetup] = useState(false);
  const [enrollCode, setEnrollCode] = useState("");
  const [isEnabling, setIsEnabling] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);

  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const [confirmPassword, setConfirmPassword] = useState("");
  const [confirmCode, setConfirmCode] = useState("");
  const [isConfirming, setIsConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);

  const handleStartSetup = async () => {
    if (!token) return;
    setSetupError(null);
    setIsStartingSetup(true);
    try {
      const data = await setupTwoFactor(token);
      setSetup(data);
    } catch (err) {
      setSetupError(err instanceof ApiError ? err.message : "Could not start setup.");
    } finally {
      setIsStartingSetup(false);
    }
  };

  const handleCancelSetup = () => {
    setSetup(null);
    setEnrollCode("");
    setSetupError(null);
  };

  const handleEnable = async (event: FormEvent) => {
    event.preventDefault();
    if (!token) return;
    setSetupError(null);
    setIsEnabling(true);
    try {
      const result = await enableTwoFactor(enrollCode.trim(), token);
      setRecoveryCodes(result.recovery_codes);
      setSetup(null);
      setEnrollCode("");
      await refreshUser();
    } catch (err) {
      setSetupError(err instanceof ApiError ? err.message : "Incorrect code. Please try again.");
    } finally {
      setIsEnabling(false);
    }
  };

  const openConfirm = (action: ConfirmAction) => {
    setConfirmAction(action);
    setConfirmPassword("");
    setConfirmCode("");
    setConfirmError(null);
  };

  const handleConfirm = async (event: FormEvent) => {
    event.preventDefault();
    if (!token || !confirmAction) return;
    setConfirmError(null);
    setIsConfirming(true);
    try {
      if (confirmAction === "disable") {
        await disableTwoFactor(confirmPassword, confirmCode.trim(), token);
        setConfirmAction(null);
        await refreshUser();
      } else {
        const result = await regenerateRecoveryCodes(confirmPassword, confirmCode.trim(), token);
        setRecoveryCodes(result.recovery_codes);
        setConfirmAction(null);
      }
    } catch (err) {
      setConfirmError(err instanceof ApiError ? err.message : "Incorrect password or code.");
    } finally {
      setIsConfirming(false);
    }
  };

  // Shown once, right after enabling or regenerating -- takes over the
  // whole card until dismissed, since leaving this page (or refreshing)
  // is exactly when these become unrecoverable.
  if (recoveryCodes) {
    return (
      <div className={styles.dangerCard}>
        <h2 className={styles.cardTitle}>Save your recovery codes</h2>
        <p className={styles.cardDescription}>
          Each code works once, if you ever lose access to your authenticator app. Store them
          somewhere safe — they won&apos;t be shown again.
        </p>
        <ul className={styles.blockerList}>
          {recoveryCodes.map((c) => (
            <li key={c}>
              <code>{c}</code>
            </li>
          ))}
        </ul>
        <button className={styles.primaryButton} onClick={() => setRecoveryCodes(null)}>
          I&apos;ve saved these
        </button>
      </div>
    );
  }

  if (setup) {
    return (
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Scan this code</h2>
        <p className={styles.cardDescription}>
          Scan with an authenticator app (Google Authenticator, 1Password, Authy), or enter the key
          manually.
        </p>
        <img
          src={`data:image/svg+xml;base64,${btoa(setup.qr_code_svg)}`}
          alt="Two-factor setup QR code"
          width={200}
          height={200}
        />
        <p className={styles.notice}>
          Manual entry key: <code>{setup.secret}</code>
        </p>
        <form onSubmit={handleEnable}>
          <input
            type="text"
            inputMode="numeric"
            placeholder="6-digit code"
            value={enrollCode}
            onChange={(e) => setEnrollCode(e.target.value)}
            required
            className={styles.input}
          />
          <div className={styles.row}>
            <button className={styles.primaryButton} type="submit" disabled={isEnabling || !enrollCode.trim()}>
              {isEnabling ? "Verifying…" : "Enable"}
            </button>
            <button type="button" className={styles.dangerButton} onClick={handleCancelSetup}>
              Cancel
            </button>
          </div>
        </form>
        {setupError && <p className={styles.error}>{setupError}</p>}
      </div>
    );
  }

  if (confirmAction) {
    return (
      <div className={styles.dangerCard}>
        <h2 className={styles.cardTitle}>
          {confirmAction === "disable" ? "Disable two-factor authentication" : "Regenerate recovery codes"}
        </h2>
        <p className={styles.cardDescription}>
          {confirmAction === "disable"
            ? "Confirm your password and a current code to turn this off."
            : "This invalidates your existing recovery codes. Confirm your password and a current code."}
        </p>
        <form onSubmit={handleConfirm}>
          <input
            type="password"
            placeholder="Password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            className={styles.input}
          />
          <input
            type="text"
            placeholder="6-digit code or recovery code"
            value={confirmCode}
            onChange={(e) => setConfirmCode(e.target.value)}
            required
            className={styles.input}
          />
          <div className={styles.row}>
            <button
              className={styles.dangerButton}
              type="submit"
              disabled={isConfirming || !confirmPassword || !confirmCode.trim()}
            >
              {isConfirming ? "Confirming…" : "Confirm"}
            </button>
            <button type="button" className={styles.primaryButton} onClick={() => setConfirmAction(null)}>
              Cancel
            </button>
          </div>
        </form>
        {confirmError && <p className={styles.error}>{confirmError}</p>}
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <h2 className={styles.cardTitle}>Two-factor authentication</h2>
      <p className={styles.cardDescription}>
        {user?.is_2fa_enabled
          ? "Enabled — you'll need a code from your authenticator app to log in."
          : "Add an extra step at login using an authenticator app."}
      </p>
      <div className={styles.row}>
        {user?.is_2fa_enabled ? (
          <>
            <button className={styles.primaryButton} onClick={() => openConfirm("regenerate")}>
              Regenerate recovery codes
            </button>
            <button className={styles.dangerButton} onClick={() => openConfirm("disable")}>
              Disable
            </button>
          </>
        ) : (
          <button className={styles.primaryButton} onClick={handleStartSetup} disabled={isStartingSetup}>
            {isStartingSetup ? "Starting…" : "Enable two-factor authentication"}
          </button>
        )}
      </div>
      {setupError && <p className={styles.error}>{setupError}</p>}
    </div>
  );
}
