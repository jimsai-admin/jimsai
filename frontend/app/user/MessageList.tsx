// frontend/app/user/MessageList.tsx
"use client";

import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import { useChatStore } from "./store";
import { useI18n } from "../i18n";

type Props = {
  apiBase: string;
  authHeaders: () => Record<string, string>;
  userId: string;
  workspaceId: string | undefined;
};

export default function MessageList({ apiBase, authHeaders, userId, workspaceId }: Props) {
  const store = useChatStore();
  const { messages, activeThreadId, loading, streaming } = store;
  const { t } = useI18n();
  const threadMessages = messages[activeThreadId] ?? [];
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom as messages grow / stream.
  const lastLen = threadMessages[threadMessages.length - 1]?.content.length ?? 0;
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [threadMessages.length, lastLen]);

  const handleRegenerate = (index: number) => {
    // Find the user message this assistant reply answered.
    let userIdx = -1;
    for (let i = index - 1; i >= 0; i -= 1) {
      if (threadMessages[i].role === "user") {
        userIdx = i;
        break;
      }
    }
    if (userIdx < 0) return;
    const userContent = threadMessages[userIdx].content;
    // Fork back to that turn: drop the old user+assistant pair (incl. a failed/500
    // bubble) so sendQuery re-adds the prompt exactly once — no duplicate user
    // message, the failed reply is replaced rather than appended.
    store.setMessages(activeThreadId, threadMessages.slice(0, userIdx));
    void store.sendQuery(userContent, apiBase, authHeaders(), userId, workspaceId);
  };

  return (
    <div className="messages">
      {threadMessages.length === 0 && !loading && (
        <div className="emptyState">
          <div className="brandMark emptyBrand">J</div>
          <p className="emptyTitle">{t("emptyTitle")}</p>
          <p className="emptySubtitle">{t("emptySubtitle")}</p>
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
          streaming={streaming && index === threadMessages.length - 1}
          onRegenerate={
            message.role === "assistant" && !streaming ? () => handleRegenerate(index) : undefined
          }
        />
      ))}

      <div ref={bottomRef} />
    </div>
  );
}
