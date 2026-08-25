"use client";

import { useState, FormEvent } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { apiFetch, ApiError } from "@/lib/api";
import type { Business } from "@/types";

export default function OverviewPage() {
  const { token } = useAuth();
  const { businesses, isLoadingBusinesses, refreshBusinesses } = useDashboard();

  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setFormError(null);
    setIsCreating(true);
    try {
      await apiFetch<Business>("/businesses", {
        method: "POST",
        authToken: token,
        body: JSON.stringify({ name, industry: industry || undefined }),
      });
      setName("");
      setIndustry("");
      await refreshBusinesses();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create business.");
    } finally {
      setIsCreating(false);
    }
  };

  // Note: full empty-state cards, revenue/profit/margin metrics, and the
  // "Upload Transactions" CTA are built out in the next step. For now this
  // preserves the business creation/listing flow from Step 1 inside the
  // new dashboard shell.
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2rem", maxWidth: 640 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Overview</h1>
        <p style={{ color: "var(--muted)", marginTop: "0.25rem" }}>
          Full business metrics are coming in the next step.
        </p>
      </div>

      <section>
        <h2 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem" }}>
          Create a business
        </h2>
        <form
          onSubmit={handleCreate}
          style={{ display: "flex", flexDirection: "column", gap: "0.75rem", maxWidth: 360 }}
        >
          <input
            type="text"
            placeholder="Business name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={inputStyle}
          />
          <input
            type="text"
            placeholder="Industry (optional)"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            style={inputStyle}
          />
          <button type="submit" disabled={isCreating} style={buttonStyle}>
            {isCreating ? "Creating…" : "Create business"}
          </button>
        </form>
        {formError && (
          <p style={{ color: "#ff6b6b", fontSize: "0.875rem", marginTop: "0.5rem" }}>
            {formError}
          </p>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem" }}>
          Your businesses
        </h2>
        {isLoadingBusinesses ? (
          <p style={{ color: "var(--muted)" }}>Loading businesses…</p>
        ) : businesses.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>
            No businesses yet — create one above to get started.
          </p>
        ) : (
          <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            {businesses.map((b) => (
              <li
                key={b.id}
                style={{
                  padding: "0.75rem 1rem",
                  borderRadius: 6,
                  border: "1px solid #2a2f3a",
                  background: "#11151d",
                }}
              >
                <strong>{b.name}</strong>
                {b.industry && <span style={{ color: "var(--muted)" }}> — {b.industry}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "0.6rem 0.75rem",
  borderRadius: 6,
  border: "1px solid #2a2f3a",
  background: "#151922",
  color: "var(--foreground)",
  fontSize: "1rem",
};

const buttonStyle: React.CSSProperties = {
  padding: "0.6rem",
  borderRadius: 6,
  border: "none",
  background: "var(--accent)",
  color: "#fff",
  fontSize: "0.95rem",
  fontWeight: 600,
  cursor: "pointer",
};
