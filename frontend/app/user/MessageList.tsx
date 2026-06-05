// frontend/app/user/MessageList.tsx
"use client";

import { useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";
import MessageBubble from "./MessageBubble";
import { useChatStore } from "./store";

type Props = {
  apiBase: string;
  authHeaders: () => Record<string, string>;
  userId: string;
  workspaceId: string | undefined;
};

export default function MessageList({ apiBase, authHeaders, userId, workspaceId }: Props) {
  const store = useChatStore();
  const { messages, activeThreadId, loading } = store;
  const threadMessages = messages[activeThreadId] ?? [];
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [threadMessages.length]);

  const handleRegenerate = (index: number) => {
    // Find the user message just before this assistant message
    const userMsg = [...threadMessages].slice(0, index).reverse().find((m) => m.role === "user");
    if (!userMsg) return;
    // Remove the current assistant message and re-send the user query
    const truncated = threadMessages.slice(0, index);
    store.setMessages(activeThreadId, truncated);
    void store.sendQuery(userMsg.content, apiBase, authHeaders(), userId, workspaceId);
  };

  return (
    <div className="messages">
      {threadMessages.length === 0 && !loading && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            flex: 1,
            gap: 12,
            color: "var(--muted)",
            paddingTop: 80,
          }}
        >
          <div className="brandMark" style={{ width: 48, height: 48, fontSize: 22 }}>
            J
          </div>
          <p style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>JimsAI</p>
          <p style={{ margin: 0, fontSize: 13, textAlign: "center", maxWidth: 300 }}>
            Start a conversation. Ask anything — code, math, science, or teach me about your workspace.
          </p>
        </div>
      )}

      {threadMessages.map((message, index) => (
        <MessageBubble
          key={`${message.role}-${index}`}
          message={message}
          messageIndex={index}
          apiBase={apiBase}
          authHeaders={authHeaders}
          userId={userId}
          workspaceId={workspaceId}
          onRegenerate={
            message.role === "assistant" ? () => handleRegenerate(index) : undefined
          }
        />
      ))}

      {loading && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--muted)", padding: "4px 0" }}>
          <Loader2 size={16} style={{ animation: "spin 0.9s linear infinite" }} />
          <span style={{ fontSize: 13 }}>JimsAI is thinking…</span>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
