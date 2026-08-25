"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { login } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main style={styles.main}>
      <form onSubmit={handleSubmit} style={styles.form}>
        <h1 style={styles.heading}>Log in</h1>

        <label style={styles.label}>
          Email
          <input
            style={styles.input}
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>

        <label style={styles.label}>
          Password
          <input
            style={styles.input}
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {error && <p style={styles.error}>{error}</p>}

        <button style={styles.button} type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Logging in…" : "Log in"}
        </button>

        <p style={styles.footerText}>
          Don&apos;t have an account? <Link href="/signup">Sign up</Link>
        </p>
      </form>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  main: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "2rem",
  },
  form: {
    width: "100%",
    maxWidth: 380,
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
  },
  heading: {
    fontSize: "1.5rem",
    fontWeight: 700,
    marginBottom: "0.5rem",
  },
  label: {
    display: "flex",
    flexDirection: "column",
    gap: "0.35rem",
    fontSize: "0.875rem",
    color: "var(--muted)",
  },
  input: {
    padding: "0.6rem 0.75rem",
    borderRadius: 6,
    border: "1px solid #2a2f3a",
    background: "#151922",
    color: "var(--foreground)",
    fontSize: "1rem",
  },
  button: {
    padding: "0.7rem",
    borderRadius: 6,
    border: "none",
    background: "var(--accent)",
    color: "#fff",
    fontSize: "1rem",
    fontWeight: 600,
    cursor: "pointer",
    marginTop: "0.5rem",
  },
  error: {
    color: "#ff6b6b",
    fontSize: "0.875rem",
  },
  footerText: {
    fontSize: "0.875rem",
    color: "var(--muted)",
    textAlign: "center",
    marginTop: "0.5rem",
  },
};
