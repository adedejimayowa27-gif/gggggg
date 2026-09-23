"use client";

/**
 * Batch 12.2: email confirmation landing page -- the link from the
 * verification email lands here with ?token=... attached, and confirms
 * automatically (no form to submit, unlike /reset-password).
 *
 * Same useSearchParams()-needs-a-Suspense-boundary requirement as
 * /reset-password/page.tsx (see that file's comment) -- split into
 * VerifyEmailContent for the same reason.
 */
import { useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Logo from "@/components/Logo";
import styles from "@/styles/auth.module.css";

type Status = "verifying" | "success" | "error";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const { user, refreshUser } = useAuth();

  const [status, setStatus] = useState<Status>("verifying");
  const [error, setError] = useState<string | null>(null);
  // Effects can run twice in React's Strict Mode (dev only); a one-time
  // verification token would fail the second call with a confusing
  // "invalid or expired" error, so this guards against that.
  const hasRun = useRef(false);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setError("This verification link is missing its token.");
      return;
    }
    if (hasRun.current) return;
    hasRun.current = true;

    apiFetch<{ message: string }>("/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token }),
    })
      .then(() => {
        setStatus("success");
        // If they're already logged in (e.g. clicked the link in the
        // same browser), refresh so the banner clears right away rather
        // than on their next login.
        if (user) void refreshUser();
      })
      .catch((err) => {
        setStatus("error");
        setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      });
    // refreshUser/user intentionally excluded: this should run once per
    // token, not re-run if the user object changes shape mid-request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className={styles.card}>
      <div>
        <h1 className={styles.heading}>Confirm your email</h1>
        <p className={styles.subheading}>
          {status === "verifying" && "Confirming your email address…"}
          {status === "success" && "Your email address is confirmed."}
          {status === "error" && "We couldn't confirm this link."}
        </p>
      </div>

      {status === "error" && (
        <p className={styles.error}>
          {error} If it&apos;s expired, log in and use &quot;Resend email&quot; from the banner at the top of the
          dashboard.
        </p>
      )}
      {status === "success" && <p className={styles.success}>Thanks for confirming your email address.</p>}

      <p className={styles.footerText}>
        <Link href={user ? "/dashboard" : "/login"}>
          {user ? "Go to dashboard" : "Back to log in"}
        </Link>
      </p>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <main className={styles.page}>
      <div className={styles.topNav}>
        <Link href="/">
          <Logo />
        </Link>
      </div>

      <div className={styles.wrap}>
        <Suspense fallback={<div className={styles.card}>Loading…</div>}>
          <VerifyEmailContent />
        </Suspense>
      </div>
    </main>
  );
}
