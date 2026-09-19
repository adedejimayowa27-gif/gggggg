"use client";

import { useDashboard } from "@/context/DashboardContext";
import AiAssistantChat from "@/components/AiAssistantChat";
import ComingSoon from "@/components/ComingSoon";
import styles from "./ai-assistant.module.css";

export default function AiAssistantPage() {
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness) {
    return (
      <ComingSoon
        title="AI Assistant"
        description="Create a business on the Overview page before chatting with the assistant."
      />
    );
  }

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h1>AI Assistant</h1>
          <p className={styles.subtitle}>Ask questions grounded in your actual sales data.</p>
        </div>
      </div>
      <AiAssistantChat businessId={primaryBusiness.id} />
    </div>
  );
}
