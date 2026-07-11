// frontend/app/user/MessageBubble.tsx
"use client";

import { useCallback, useState } from "react";
import { Copy, Check, ThumbsUp, ThumbsDown, Layers3, RotateCcw, Pencil, ShieldCheck } from "lucide-react";
import MarkdownRenderer from "./MarkdownRenderer";
import { useChatStore } from "./store";
import { useI18n } from "../i18n";
import type { Message } from "./types";

type Props = {
  message: Message;
  messageIndex: number;
  apiBase: string;
  authHeaders: () => Record<string, string>;
  userId: string;
  workspaceId: string | undefined;
  onRegenerate?: () => void;
  streaming?: boolean;
};

export default function MessageBubble({
  message,
  messageIndex,
  apiBase,
  authHeaders,
  userId,
  workspaceId,
  onRegenerate,
  streaming,
}: Props) {
  const store = useChatStore();
  const { t } = useI18n();
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  const copyResponse = useCallback(() => {
    navigator.clipboard.writeText(message.content).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1400);
      },
      () => {}
    );
  }, [message.content]);

  const editPrompt = useCallback(() => {
    store.setPendingEdit(message.content);
  }, [store, message.content]);

  const handleThumbsUp = useCallback(async () => {
    await store.submitFeedback("positive", message, "", apiBase, authHeaders(), userId, workspaceId);
  }, [store, message, apiBase, authHeaders, userId, workspaceId]);

  const handleThumbsDown = useCallback(async () => {
    await store.submitFeedback("negative", message, "", apiBase, authHeaders(), userId, workspaceId);
  }, [store, message, apiBase, authHeaders, userId, workspaceId]);

  const handleInsights = useCallback(() => {
    store.openDrawer(messageIndex, "answer");
  }, [store, messageIndex]);

  const api = message.apiResponse;
  const grounded = !!api && !(api.used_llm ?? api.used_groq);
  const confidence = api?.confidence ?? 0;
  const gaps = api?.gaps ?? [];
  const isEmptyStreaming = !isUser && streaming && message.content.length === 0;

  return (
    <div className={`messageBubbleWrapper ${isUser ? "user" : "assistant"}`}>
      <article className={`message ${isUser ? "user" : ""}`}>
        <span className="messageRole">{isUser ? "You" : "JimsAI"}</span>
        {isEmptyStreaming ? (
          <div className="typingDots" aria-label={t("thinking")}>
            <span /><span /><span />
          </div>
        ) : (
          <MarkdownRenderer content={message.content} />
        )}
        {!isUser && streaming && message.content.length > 0 && <span className="streamCaret" />}
      </article>

      {/* JimsAI honesty badges — grounded/no-LLM, confidence, gaps */}
      {!isUser && api && !isEmptyStreaming && (
        <div className="msgBadges">
          {grounded ? (
            <span className="badge good"><ShieldCheck size={11} /> {t("grounded")}</span>
          ) : (
            <span className="badge">{t("viaModel")}</span>
          )}
          {confidence > 0 && (
            <span className="badge">{Math.round(confidence * 100)}% {t("confidence")}</span>
          )}
          {gaps.length > 0 && <span className="badge warn">{gaps.length} {t("gaps")}</span>}
        </div>
      )}

      <div className={`messageActions ${isUser ? "userActions" : ""}`}>
        <button title={copied ? t("copied") : t("copy")} onClick={copyResponse} type="button">
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
        {isUser ? (
          <button title={t("edit")} onClick={editPrompt} type="button">
            <Pencil size={14} />
          </button>
        ) : (
          <>
            <button title={t("goodResponse")} onClick={handleThumbsUp} type="button">
              <ThumbsUp size={14} />
            </button>
            <button title={t("badResponse")} onClick={handleThumbsDown} type="button">
              <ThumbsDown size={14} />
            </button>
            <button title={t("insights")} className="insightsButton" onClick={handleInsights} type="button">
              <Layers3 size={14} />
            </button>
            {onRegenerate && (
              <button title={t("regenerate")} onClick={onRegenerate} type="button">
                <RotateCcw size={14} />
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
