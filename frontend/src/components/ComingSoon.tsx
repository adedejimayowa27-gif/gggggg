interface Props {
  title: string;
  description?: string;
}

export default function ComingSoon({ title, description }: Props) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        gap: "0.5rem",
        padding: "3rem 1rem",
      }}
    >
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700 }}>{title}</h1>
      <p style={{ color: "var(--muted)", maxWidth: 420 }}>
        {description || "This section is coming in a future step."}
      </p>
    </div>
  );
}
