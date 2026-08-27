"use client";

/**
 * Chat UI for the AI assistant (Batch 5.3's
 * POST /businesses/{business_id}/assistant/messages).
 *
 * On mount, loads the business's most recent conversation (if one
 * exists) and its messages, so refreshing the page doesn't lose
 * context -- the conversation itself is Batch 5.2 state, this
 * component just reads it back.
 */
import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiFetch, ApiError } from "@/lib/api";
import type { AssistantMessageResponse, ChatConversation, ChatMessage } from "@/types";
import styles from "./AiAssistantChat.module.css";

interface Props {
  businessId: string;
}

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  pending?: boolean;
  failed?: boolean;
}

const SUGGESTIONS = [
  "What was my revenue last month?",
  "Which products are my top sellers this month?",
  "How does this month compare to last month?",
];

function toDisplayMessage(message: ChatMessage): DisplayMessage {
  return {
    id: message.id,
    role: message.role === "assistant" ? "assistant" : "user",
    content: message.content,
    created_at: message.created_at,
  };
}

function formatTime(iso?: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function AiAssistantChat({ businessId }: Props) {
  const { token } = useAuth();

  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load the most recent conversation (if any) and its messages on mount,
  // so a page refresh picks up where the user left off instead of
  // starting a fresh, empty chat every time.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    async function loadHistory() {
      setIsLoadingHistory(true);
      setLoadError(null);
      try {
        const conversations = await apiFetch<ChatConversation[]>(
          `/businesses/${businessId}/conversations`,
          { authToken: token ?? undefined }
        );
        if (cancelled) return;

        if (conversations.length === 0) {
          setConversationId(null);
          setMessages([]);
          return;
        }

        // The list route already orders newest-first.
        const mostRecent = conversations[0];
        const history = await apiFetch<ChatMessage[]>(
          `/businesses/${businessId}/conversations/${mostRecent.id}/messages`,
          { authToken: token ?? undefined }
        );
        if (cancelled) return;

        setConversationId(mostRecent.id);
        setMessages(history.map(toDisplayMessage));
      } catch (err) {
        if (cancelled) return;
        setLoadError(
          err instanceof ApiError ? err.message : "Couldn't load your conversation history."
        );
      } finally {
        if (!cancelled) setIsLoadingHistory(false);
      }
    }

    loadHistory();
    return () => {
      cancelled = true;
    };
  }, [businessId, token]);

  // Keep the latest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isSending || !token) return;

      const tempId = `temp-${Date.now()}`;
      setMessages((prev) => [...prev, { id: tempId, role: "user", content: trimmed, pending: true }]);
      setInputValue("");
      setIsSending(true);
      setSendError(null);

      try {
        const data = await apiFetch<AssistantMessageResponse>(
          `/businesses/${businessId}/assistant/messages`,
          {
            method: "POST",
            authToken: token,
            body: JSON.stringify({ conversation_id: conversationId, message: trimmed }),
          }
        );

        setConversationId(data.conversation_id);
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== tempId),
          toDisplayMessage(data.user_message),
          toDisplayMessage(data.assistant_message),
        ]);
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) => (m.id === tempId ? { ...m, pending: false, failed: true } : m))
        );
        setSendError(
          err instanceof ApiError ? err.message : "Something went wrong. Please try again."
        );
      } finally {
        setIsSending(false);
      }
    },
    [businessId, conversationId, isSending, token]
  );

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage(inputValue);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(inputValue);
    }
  };

  const hasMessages = messages.length > 0;

  return (
    <div>
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "1.25rem" }}>
        AI Assistant
      </h1>

      <div className={styles.wrap}>
        <div className={styles.messages}>
          {isLoadingHistory ? (
            <div className={styles.centerFill}>
              <p style={{ color: "var(--muted)" }}>Loading conversation…</p>
            </div>
          ) : loadError ? (
            <div className={styles.centerFill}>
              <p style={{ color: "#ff6b6b" }}>{loadError}</p>
            </div>
          ) : !hasMessages ? (
            <div className={styles.centerFill}>
              <p className={styles.emptyTitle}>Ask about your business numbers</p>
              <p className={styles.emptyText}>
                Revenue, profit, top products, comparisons across periods -- anything grounded
                in your actual sales data.
              </p>
              <div className={styles.suggestions}>
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={styles.suggestionChip}
                    onClick={() => sendMessage(s)}
                    disabled={isSending}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`${styles.bubbleRow} ${
                    m.role === "user" ? styles.bubbleRowUser : styles.bubbleRowAssistant
                  }`}
                >
                  <div
                    className={`${styles.bubble} ${
                      m.role === "user" ? styles.bubbleUser : styles.bubbleAssistant
                    } ${m.pending ? styles.bubblePending : ""} ${
                      m.failed ? styles.bubbleFailed : ""
                    }`}
                  >
                    <div className={styles.bubbleText}>{m.content}</div>
                    {m.created_at && !m.pending && (
                      <div className={styles.bubbleTime}>{formatTime(m.created_at)}</div>
                    )}
                    {m.failed && <div className={styles.bubbleFailedText}>Failed to send</div>}
                  </div>
                </div>
              ))}

              {isSending && (
                <div className={`${styles.bubbleRow} ${styles.bubbleRowAssistant}`}>
                  <div className={`${styles.bubble} ${styles.bubbleAssistant}`}>
                    <div className={styles.typingDots}>
                      <span />
                      <span />
                      <span />
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>

        <form className={styles.inputRow} onSubmit={handleSubmit}>
          <textarea
            ref={textareaRef}
            className={styles.textarea}
            placeholder="Ask about revenue, profit, top products…"
            rows={1}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoadingHistory}
          />
          <button
            type="submit"
            className={styles.sendButton}
            disabled={isLoadingHistory || isSending || !inputValue.trim()}
          >
            Send
          </button>
        </form>
        {sendError && <div className={styles.sendError}>{sendError}</div>}
      </div>
    </div>
  );
}
