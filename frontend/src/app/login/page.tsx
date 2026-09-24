"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import Logo from "@/components/Logo";
import styles from "@/styles/auth.module.css";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Batch 12.6: set once POST /auth/login comes back asking for a 2FA
  // code instead of tokens -- see AuthContext's login() return shape.
  // Presence of a challenge token is what switches this form from
  // email+password to a single code field.
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [code, setCode] = useState("");

  const { login, verifyTwoFactorLogin } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.twoFactorRequired) {
        setChallengeToken(result.challengeToken);
      } else {
        router.push("/dashboard");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerifyCode = async (e: FormEvent) => {
    e.preventDefault();
    if (!challengeToken) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await verifyTwoFactorLogin(challengeToken, code.trim());
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Incorrect code. Please try again.");
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
          {!challengeToken ? (
            <>
              <div>
                <h1 className={styles.heading}>Welcome back</h1>
                <p className={styles.subheading}>Log in to see where your business stands.</p>
              </div>

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

                <label className={styles.label}>
                  Password
                  <input
                    className={styles.input}
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                </label>

                <p className={styles.footerText} style={{ textAlign: "right", marginTop: "-0.5rem" }}>
                  <Link href="/forgot-password">Forgot password?</Link>
                </p>

                {error && <p className={styles.error}>{error}</p>}

                <button className={styles.button} type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Logging in…" : "Log in"}
                </button>
              </form>

              <p className={styles.footerText}>
                Don&apos;t have an account? <Link href="/signup">Sign up</Link>
              </p>
            </>
          ) : (
            <>
              <div>
                <h1 className={styles.heading}>Enter your code</h1>
                <p className={styles.subheading}>
                  Open your authenticator app, or use one of your recovery codes.
                </p>
              </div>

              <form onSubmit={handleVerifyCode} className={styles.form}>
                <label className={styles.label}>
                  Code
                  <input
                    className={styles.input}
                    type="text"
                    inputMode="numeric"
                    autoFocus
                    required
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="123456"
                  />
                </label>

                {error && <p className={styles.error}>{error}</p>}

                <button className={styles.button} type="submit" disabled={isSubmitting || !code.trim()}>
                  {isSubmitting ? "Verifying…" : "Verify"}
                </button>
              </form>

              <p className={styles.footerText}>
                <button
                  type="button"
                  style={{
                    background: "none",
                    border: "none",
                    padding: 0,
                    font: "inherit",
                    color: "inherit",
                    textDecoration: "underline",
                    cursor: "pointer",
                  }}
                  onClick={() => {
                    setChallengeToken(null);
                    setCode("");
                    setError(null);
                  }}
                >
                  Back to login
                </button>
              </p>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
