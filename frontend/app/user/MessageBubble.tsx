// frontend/app/user/MessageBubble.tsx
"use client";

import { useCallback } from "react";
import { Copy, ThumbsUp, ThumbsDown, Layers3, RotateCcw } from "lucide-react";
import MarkdownRenderer from "./MarkdownRenderer";
import { useChatStore } from "./store";
import type { Message } from "./types";

type Props = {
  message: Message;
  messageIndex: number;
  apiBase: string;
  authHeaders: () => Record<string, string>;
  userId: string;
  workspaceId: string | undefined;
  onRegenerate?: () => void;
};

export default function MessageBubble({
  message,
  messageIndex,
  apiBase,
  authHeaders,
  userId,
  workspaceId,
  onRegenerate,
}: Props) {
  const store = useChatStore();
  const isUser = message.role === "user";

  const copyResponse = useCallback(() => {
    navigator.clipboard.writeText(message.content).catch(() => {});
  }, [message.content]);

  const handleThumbsUp = useCallback(async () => {
    await store.submitFeedback("positive", message, "", apiBase, authHeaders(), userId, workspaceId);
  }, [store, message, apiBase, authHeaders, userId, workspaceId]);

  const handleThumbsDown = useCallback(async () => {
    await store.submitFeedback("negative", message, "", apiBase, authHeaders(), userId, workspaceId);
  }, [store, message, apiBase, authHeaders, userId, workspaceId]);

  const handleInsights = useCallback(() => {
    store.openDrawer(messageIndex, "answer");
  }, [store, messageIndex]);

  return (
    <div className={`messageBubbleWrapper ${isUser ? "user" : "assistant"}`}>
      <article className={`message ${isUser ? "user" : ""}`}>
        <span className="messageRole">{isUser ? "You" : "JimsAI"}</span>
        <MarkdownRenderer content={message.content} />
      </article>
      {!isUser && (
        <div className="messageActions">
          <button title="Copy response" onClick={copyResponse} type="button">
            <Copy size={14} />
          </button>
          <button title="Good response" onClick={handleThumbsUp} type="button">
            <ThumbsUp size={14} />
          </button>
          <button title="Bad response" onClick={handleThumbsDown} type="button">
            <ThumbsDown size={14} />
          </button>
          <button
            title="View insights"
            className="insightsButton"
            onClick={handleInsights}
            type="button"
          >
            <Layers3 size={14} />
          </button>
          {onRegenerate && (
            <button title="Regenerate" onClick={onRegenerate} type="button">
              <RotateCcw size={14} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
