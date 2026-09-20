"use client";

/**
 * Forgot-password request page.
 *
 * Always shows the same success message on submit, whether or not the
 * email matches an account -- mirrors the backend's enumeration-safe
 * response (see routes/auth.py's forgot_password), so the frontend
 * doesn't undo that protection by, say, showing a different message
 * for "email not found."
 */
import { useState, FormEvent } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import Logo from "@/components/Logo";
import styles from "@/styles/auth.module.css";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await apiFetch<{ message: string }>("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setSubmitted(true);
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
            <h1 className={styles.heading}>Reset your password</h1>
            <p className={styles.subheading}>
              Enter the email on your account and we&rsquo;ll send you a reset link.
            </p>
          </div>

          {submitted ? (
            <p className={styles.success}>
              If an account exists for that email, a reset link has been sent. Check your inbox.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className={styles.form}>
              <label className={styles.label}>
                Email
                <input
                  className={styles.input}
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
              </label>

              {error && <p className={styles.error}>{error}</p>}

              <button className={styles.button} type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Sending…" : "Send reset link"}
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
