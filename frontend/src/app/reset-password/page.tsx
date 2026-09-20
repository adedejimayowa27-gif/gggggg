"use client";

/**
 * Password reset completion page -- the link from the reset email lands
 * here with ?token=... attached.
 */
import { useState, FormEvent } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import Logo from "@/components/Logo";
import styles from "@/styles/auth.module.css";

export default function ResetPasswordPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await apiFetch<{ message: string }>("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      setSuccess(true);
      setTimeout(() => router.push("/login"), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className={styles.page}>
      <div className={styles.topNav}>
        <Link href="/">
          <Logo />
        </Link>
      </div>

      <div className={styles.wrap}>
        <div className={styles.card}>
          <div>
            <h1 className={styles.heading}>Set a new password</h1>
            <p className={styles.subheading}>Choose a new password for your account.</p>
          </div>

          {!token ? (
            <p className={styles.error}>
              This reset link is missing its token. Request a new one from the{" "}
              <Link href="/forgot-password">forgot password</Link> page.
            </p>
          ) : success ? (
            <p className={styles.success}>Password updated. Taking you to log in…</p>
          ) : (
            <form onSubmit={handleSubmit} className={styles.form}>
              <label className={styles.label}>
                New password
                <input
                  className={styles.input}
                  type="password"
                  required
                  minLength={8}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••"
                />
              </label>

              {error && <p className={styles.error}>{error}</p>}

              <button className={styles.button} type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Updating…" : "Update password"}
              </button>
            </form>
          )}

          <p className={styles.footerText}>
            <Link href="/login">Back to log in</Link>
          </p>
        </div>
      </div>
    </main>
  );
}
