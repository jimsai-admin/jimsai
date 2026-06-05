// frontend/app/user/Composer.tsx
"use client";

import {
  useRef,
  useCallback,
  type FormEvent,
  type KeyboardEvent,
  type ChangeEvent,
} from "react";
import { Paperclip, Send, GitBranch, Lightbulb, Loader2 } from "lucide-react";
import { useChatStore } from "./store";

type Props = {
  apiBase: string;
  authHeaders: () => Record<string, string>;
  userId: string;
  workspaceId: string | undefined;
};

export default function Composer({ apiBase, authHeaders, userId, workspaceId }: Props) {
  const store = useChatStore();
  const { loading, canvasHint, inventionHint } = store;
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const valueRef = useRef("");

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, []);

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      valueRef.current = e.target.value;
      resize();
    },
    [resize]
  );

  const submit = useCallback(async () => {
    const query = valueRef.current.trim();
    if (!query || loading) return;
    if (textareaRef.current) {
      textareaRef.current.value = "";
      textareaRef.current.style.height = "auto";
    }
    valueRef.current = "";
    await store.sendQuery(query, apiBase, authHeaders(), userId, workspaceId);
  }, [loading, store, apiBase, authHeaders, userId, workspaceId]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // Enter submits; Shift+Enter inserts newline (default browser behavior)
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void submit();
      }
    },
    [submit]
  );

  const handleFileChange = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const text = await file.text();
      if (textareaRef.current) {
        const current = textareaRef.current.value;
        textareaRef.current.value = current ? `${current}\n\n${text}` : text;
        valueRef.current = textareaRef.current.value;
        resize();
      }
      e.target.value = "";
    },
    [resize]
  );

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      void submit();
    },
    [submit]
  );

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <input ref={fileInputRef} type="file" hidden onChange={handleFileChange} />
      <button
        className="iconButton"
        type="button"
        title="Attach file"
        onClick={() => fileInputRef.current?.click()}
      >
        <Paperclip size={18} />
      </button>

      <textarea
        ref={textareaRef}
        rows={1}
        defaultValue=""
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder="Ask JimsAI anything…"
        aria-label="Message input"
        disabled={loading}
      />

      <div className="composerActions">
        <button
          className={`hintToggle${canvasHint ? " active" : ""}`}
          type="button"
          title="Canvas route"
          onClick={() => store.setCanvasHint(!canvasHint)}
        >
          <GitBranch size={15} />
        </button>
        <button
          className={`hintToggle${inventionHint ? " active" : ""}`}
          type="button"
          title="Invention route"
          onClick={() => store.setInventionHint(!inventionHint)}
        >
          <Lightbulb size={15} />
        </button>
        <span className="composerModelLabel">Qwen3</span>
        <button className="sendButton" type="submit" disabled={loading}>
          {loading ? (
            <Loader2 size={16} style={{ animation: "spin 0.9s linear infinite" }} />
          ) : (
            <Send size={16} />
          )}
          <span>{loading ? "Running" : "Send"}</span>
        </button>
      </div>
    </form>
  );
}
