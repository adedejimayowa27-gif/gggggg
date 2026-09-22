"use client";

/**
 * Batch 12.2: a dismissible reminder shown across every dashboard page
 * while the signed-in user's email is still unverified. This is purely
 * informational -- nothing in the app is gated on verification (see
 * backend/app/api/routes/auth.py's module docstring) -- so dismissing it
 * only hides it for this browser tab's session; it reappears on the next
 * visit until the address is actually confirmed.
 */
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiFetch, ApiError } from "@/lib/api";
import styles from "./VerifyEmailBanner.module.css";

export default function VerifyEmailBanner() {
  const { user } = useAuth();
  const [isDismissed, setIsDismissed] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user || user.is_email_verified || isDismissed) {
    return null;
  }

  const handleResend = async () => {
    setError(null);
    setIsSending(true);
    try {
      await apiFetch<{ message: string }>("/auth/resend-verification", {
        method: "POST",
        body: JSON.stringify({ email: user.email }),
      });
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't send the email. Try again.");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className={styles.banner} role="status">
      <span className={styles.text}>
        {sent ? (
          <>Confirmation email sent to <strong>{user.email}</strong>. Check your inbox.</>
        ) : (
          <>
            Please confirm your email address (<strong>{user.email}</strong>).
            {error && <span className={styles.errorText}> {error}</span>}
          </>
        )}
      </span>
      <span className={styles.actions}>
        {!sent && (
          <button className={styles.link} onClick={handleResend} disabled={isSending}>
            {isSending ? "Sending…" : "Resend email"}
          </button>
        )}
        <button
          className={styles.link}
          onClick={() => setIsDismissed(true)}
          aria-label="Dismiss"
        >
          Dismiss
        </button>
      </span>
    </div>
  );
}
