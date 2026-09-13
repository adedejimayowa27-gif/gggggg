"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import type { AssistantMessageResponse } from "@/types";
import styles from "./AIBusinessBrief.module.css";

interface Props {
  businessId: string;
  token: string;
  /** Only generate a brief once there's real data to brief on -- an AI
   * summary of zero transactions is either nonsense or, worse, invites
   * the model to guess/hallucinate something plausible-sounding. */
  hasData: boolean;
}

const PROMPT =
  "Give me a short business brief for right now: 2-3 sentences on how revenue is trending and which " +
  "product is driving the most of it, then one specific, concrete recommended action I should consider " +
  "this week. Keep the whole thing tight -- no headers, no bullet points, just plain sentences.";

function cacheKey(businessId: string): string {
  const today = new Date().toISOString().slice(0, 10);
  return `bizintel:aiBrief:${businessId}:${today}`;
}

export default function AIBusinessBrief({ businessId, token, hasData }: Props) {
  const [brief, setBrief] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!hasData) return;

    // Generated at most once per business per day (cached in
    // sessionStorage) -- this calls a real LLM through the existing AI
    // assistant endpoint, so refetching on every visit to the Overview
    // page would mean a real, billed model call every single time
    // someone just glances at their dashboard, for a brief that's very
    // unlikely to have changed since this morning.
    const key = cacheKey(businessId);
    const cached = window.sessionStorage.getItem(key);
    if (cached) {
      setBrief(cached);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    apiFetch<AssistantMessageResponse>(`/businesses/${businessId}/assistant/messages`, {
      method: "POST",
      authToken: token,
      body: JSON.stringify({ conversation_id: null, message: PROMPT }),
    })
      .then((data) => {
        if (cancelled) return;
        setBrief(data.assistant_message.content);
        window.sessionStorage.setItem(key, data.assistant_message.content);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not generate a brief right now.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [businessId, token, hasData]);

  if (!hasData) return null;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.sparkleIcon} aria-hidden="true">
          <svg viewBox="0 0 20 20" width="16" height="16">
            <path d="M10 2L12 10L10 18L8 10Z" fill="currentColor" />
            <path d="M2 10L10 8.5L18 10L10 11.5Z" fill="currentColor" />
          </svg>
        </span>
        <span className={styles.title}>AI Business Brief</span>
      </div>

      {isLoading && (
        <div className={styles.skeleton}>
          <span className={styles.skeletonLine} />
          <span className={styles.skeletonLine} />
          <span className={`${styles.skeletonLine} ${styles.skeletonShort}`} />
        </div>
      )}

      {!isLoading && error && <p className={styles.error}>{error}</p>}

      {!isLoading && !error && brief && <p className={styles.briefText}>{brief}</p>}

      <Link href="/dashboard/ai-assistant" className={styles.askLink}>
        Ask AI →
      </Link>
    </div>
  );
}
