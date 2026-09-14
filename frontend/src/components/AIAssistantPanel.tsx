"use client";

import { useState, FormEvent } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import type { AssistantMessageResponse } from "@/types";
import styles from "./AIAssistantPanel.module.css";

interface Props {
  businessId: string;
  token: string;
}

const SUGGESTED_QUESTIONS = [
  "Why is my revenue up this month?",
  "Which product is performing best?",
  "What are my top customers?",
  "Give me a growth forecast",
];

export default function AIAssistantPanel({ businessId, token }: Props) {
  const [inputValue, setInputValue] = useState("");
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || isLoading) return;

    setLastQuestion(trimmed);
    setAnswer(null);
    setError(null);
    setIsLoading(true);
    setInputValue("");

    // Same real endpoint AIBusinessBrief and the full AI Assistant page
    // use -- a genuine answer grounded in this business's own data, not
    // a canned response. conversation_id is carried across questions
    // asked in this panel so a follow-up has the prior context, exactly
    // like the full chat page.
    apiFetch<AssistantMessageResponse>(`/businesses/${businessId}/assistant/messages`, {
      method: "POST",
      authToken: token,
      body: JSON.stringify({ conversation_id: conversationId, message: trimmed }),
    })
      .then((data) => {
        setConversationId(data.conversation_id);
        setAnswer(data.assistant_message.content);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not get an answer right now.");
      })
      .finally(() => setIsLoading(false));
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    ask(inputValue);
  };

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h2 className={styles.title}>Your AI Assistant</h2>
        <p className={styles.subtitle}>Ask anything about your business…</p>
      </div>

      {!lastQuestion && (
        <div className={styles.suggestions}>
          {SUGGESTED_QUESTIONS.map((question) => (
            <button key={question} className={styles.suggestionChip} onClick={() => ask(question)}>
              {question}
            </button>
          ))}
        </div>
      )}

      {lastQuestion && (
        <div className={styles.conversation}>
          <p className={styles.questionText}>{lastQuestion}</p>
          {isLoading && (
            <div className={styles.skeleton}>
              <span className={styles.skeletonLine} />
              <span className={`${styles.skeletonLine} ${styles.skeletonShort}`} />
            </div>
          )}
          {!isLoading && error && <p className={styles.error}>{error}</p>}
          {!isLoading && answer && <p className={styles.answerText}>{answer}</p>}
          <Link href="/dashboard/ai-assistant" className={styles.continueLink}>
            Continue in full chat →
          </Link>
        </div>
      )}

      <form className={styles.form} onSubmit={handleSubmit}>
        <input
          className={styles.input}
          type="text"
          placeholder="Ask a question…"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          disabled={isLoading}
        />
        <button type="submit" className={styles.sendButton} disabled={isLoading || !inputValue.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}
