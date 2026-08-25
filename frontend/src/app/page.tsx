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
        gap: "1rem",
      }}
    >
      <h1 style={{ fontSize: "2rem", fontWeight: 700 }}>BizIntel Platform</h1>
      <p style={{ color: "var(--muted)", maxWidth: 480 }}>
        Project foundation is running. The full landing page, authentication
        flow, and dashboard are built in the next steps.
      </p>
    </main>
  );
}
