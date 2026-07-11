// frontend/app/user/Composer.tsx
"use client";

import {
  useEffect,
  useRef,
  useState,
  useCallback,
  type FormEvent,
  type KeyboardEvent,
  type ChangeEvent,
} from "react";
import { Paperclip, Send, GitBranch, Lightbulb, Square } from "lucide-react";
import { useChatStore } from "./store";
import { useI18n } from "../i18n";

type Props = {
  apiBase: string;
  authHeaders: () => Record<string, string>;
  userId: string;
  workspaceId: string | undefined;
};

export default function Composer({ apiBase, authHeaders, userId, workspaceId }: Props) {
  const store = useChatStore();
  const { loading, streaming, canvasHint, inventionHint, pendingEdit } = store;
  const { t } = useI18n();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, []);

  useEffect(() => {
    resize();
  }, [value, resize]);

  // Edit-prompt: load a previous user message into the composer and focus it.
  useEffect(() => {
    if (pendingEdit) {
      setValue(pendingEdit);
      store.setPendingEdit("");
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (el) {
          el.focus();
          el.setSelectionRange(el.value.length, el.value.length);
        }
      });
    }
  }, [pendingEdit, store]);

  const submit = useCallback(async () => {
    const query = value.trim();
    if (!query || loading) return;
    setValue("");
    await store.sendQuery(query, apiBase, authHeaders(), userId, workspaceId);
  }, [value, loading, store, apiBase, authHeaders, userId, workspaceId]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // Enter submits; Shift+Enter inserts a newline.
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void submit();
      }
    },
    [submit]
  );

  const handleChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
  }, []);

  const handleFileChange = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const text = await file.text();
      setValue((v) => (v ? `${v}\n\n${text}` : text));
      e.target.value = "";
    },
    []
  );

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      void submit();
    },
    [submit]
  );

  return (
    <div className="composerWrap">
      <form className="composer" onSubmit={handleSubmit}>
        <input ref={fileInputRef} type="file" hidden onChange={handleFileChange} />
        <button
          className="iconButton"
          type="button"
          title={t("attach")}
          aria-label={t("attach")}
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip size={18} />
        </button>

        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={t("composerPlaceholder")}
          aria-label={t("messageInput")}
        />

        <div className="composerActions">
          <button
            className={`hintToggle${canvasHint ? " active" : ""}`}
            type="button"
            title={t("canvasRoute")}
            aria-pressed={canvasHint}
            onClick={() => store.setCanvasHint(!canvasHint)}
          >
            <GitBranch size={15} />
          </button>
          <button
            className={`hintToggle${inventionHint ? " active" : ""}`}
            type="button"
            title={t("inventionRoute")}
            aria-pressed={inventionHint}
            onClick={() => store.setInventionHint(!inventionHint)}
          >
            <Lightbulb size={15} />
          </button>
          {streaming ? (
            <button
              className="sendButton stopButton"
              type="button"
              onClick={() => store.stopStreaming()}
              title={t("stop")}
            >
              <Square size={14} fill="currentColor" />
              <span>{t("stop")}</span>
            </button>
          ) : (
            <button className="sendButton" type="submit" disabled={!value.trim()} title={t("send")}>
              <Send size={16} />
              <span>{t("send")}</span>
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
