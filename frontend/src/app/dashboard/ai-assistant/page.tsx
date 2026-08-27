"use client";

import { useDashboard } from "@/context/DashboardContext";
import AiAssistantChat from "@/components/AiAssistantChat";

export default function AiAssistantPage() {
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness) {
    return (
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.5rem" }}>
          AI Assistant
        </h1>
        <p style={{ color: "var(--muted)" }}>
          Create a business on the Overview page before chatting with the assistant.
        </p>
      </div>
    );
  }

  return <AiAssistantChat businessId={primaryBusiness.id} />;
}
