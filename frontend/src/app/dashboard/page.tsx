"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { apiFetch, ApiError } from "@/lib/api";
import type { Business } from "@/types";

export default function DashboardPage() {
  const { user, token, isLoading, logout } = useAuth();
  const router = useRouter();

  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [isFetching, setIsFetching] = useState(true);
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Route protection: redirect unauthenticated users to login once the
  // initial auth check has finished.
  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/login");
    }
  }, [isLoading, user, router]);

  useEffect(() => {
    if (!token) return;
    apiFetch<Business[]>("/businesses", { authToken: token })
      .then(setBusinesses)
      .catch(() => setBusinesses([]))
      .finally(() => setIsFetching(false));
  }, [token]);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setFormError(null);
    setIsCreating(true);
    try {
      const business = await apiFetch<Business>("/businesses", {
        method: "POST",
        authToken: token,
        body: JSON.stringify({ name, industry: industry || undefined }),
      });
      setBusinesses((prev) => [business, ...prev]);
      setName("");
      setIndustry("");
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create business.");
    } finally {
      setIsCreating(false);
    }
  };

  if (isLoading || !user) {
    return (
      <main style={styles.centered}>
        <p style={{ color: "var(--muted)" }}>Loading…</p>
      </main>
    );
  }

  return (
    <main style={styles.main}>
      <header style={styles.header}>
        <div>
          <h1 style={styles.heading}>Welcome, {user.full_name || user.email}</h1>
          <p style={{ color: "var(--muted)" }}>{user.email}</p>
        </div>
        <button style={styles.logoutButton} onClick={() => logout()}>
          Log out
        </button>
      </header>

      <section style={styles.section}>
        <h2 style={styles.subheading}>Create a business</h2>
        <form onSubmit={handleCreate} style={styles.form}>
          <input
            style={styles.input}
            type="text"
            placeholder="Business name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            style={styles.input}
            type="text"
            placeholder="Industry (optional)"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
          />
          <button style={styles.button} type="submit" disabled={isCreating}>
            {isCreating ? "Creating…" : "Create business"}
          </button>
        </form>
        {formError && <p style={styles.error}>{formError}</p>}
      </section>

      <section style={styles.section}>
        <h2 style={styles.subheading}>Your businesses</h2>
        {isFetching ? (
          <p style={{ color: "var(--muted)" }}>Loading businesses…</p>
        ) : businesses.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>
            No businesses yet — create one above to get started.
          </p>
        ) : (
          <ul style={styles.list}>
            {businesses.map((b) => (
              <li key={b.id} style={styles.listItem}>
                <strong>{b.name}</strong>
                {b.industry && <span style={{ color: "var(--muted)" }}> — {b.industry}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  main: {
    minHeight: "100vh",
    maxWidth: 640,
    margin: "0 auto",
    padding: "3rem 1.5rem",
    display: "flex",
    flexDirection: "column",
    gap: "2.5rem",
  },
  centered: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  heading: {
    fontSize: "1.5rem",
    fontWeight: 700,
  },
  subheading: {
    fontSize: "1.1rem",
    fontWeight: 600,
    marginBottom: "1rem",
  },
  section: {
    display: "flex",
    flexDirection: "column",
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "0.75rem",
    maxWidth: 360,
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
    padding: "0.6rem",
    borderRadius: 6,
    border: "none",
    background: "var(--accent)",
    color: "#fff",
    fontSize: "0.95rem",
    fontWeight: 600,
    cursor: "pointer",
  },
  logoutButton: {
    padding: "0.5rem 1rem",
    borderRadius: 6,
    border: "1px solid #2a2f3a",
    background: "transparent",
    color: "var(--foreground)",
    fontSize: "0.875rem",
    cursor: "pointer",
  },
  error: {
    color: "#ff6b6b",
    fontSize: "0.875rem",
    marginTop: "0.5rem",
  },
  list: {
    listStyle: "none",
    display: "flex",
    flexDirection: "column",
    gap: "0.6rem",
  },
  listItem: {
    padding: "0.75rem 1rem",
    borderRadius: 6,
    border: "1px solid #2a2f3a",
    background: "#11151d",
  },
};
