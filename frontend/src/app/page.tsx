import Link from "next/link";

export default function Home() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: "2rem",
        gap: "1.5rem",
      }}
    >
      <h1 style={{ fontSize: "2rem", fontWeight: 700 }}>BizIntel Platform</h1>
      <p style={{ color: "var(--muted)", maxWidth: 480 }}>
        Project foundation is running. The full landing page, AI assistant,
        forecasting, and simulator are built in later steps — for now you can
        sign up and create a business.
      </p>
      <div style={{ display: "flex", gap: "1rem" }}>
        <Link
          href="/signup"
          style={{
            padding: "0.7rem 1.4rem",
            borderRadius: 6,
            background: "var(--accent)",
            color: "#fff",
            fontWeight: 600,
          }}
        >
          Sign up
        </Link>
        <Link
          href="/login"
          style={{
            padding: "0.7rem 1.4rem",
            borderRadius: 6,
            border: "1px solid #2a2f3a",
            color: "var(--foreground)",
            fontWeight: 600,
          }}
        >
          Log in
        </Link>
      </div>
    </main>
  );
}
