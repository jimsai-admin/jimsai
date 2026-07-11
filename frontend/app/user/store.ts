// frontend/app/user/store.ts
"use client";

import { create } from "zustand";
import type { Thread, Message, ApiResponse } from "./types";

function createThreadId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `thread_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function getStoredThreadId(): string {
  if (typeof window === "undefined") return createThreadId();
  return window.localStorage.getItem("jimsai:active-thread") || createThreadId();
}

function persistThreadId(id: string): void {
  try {
    if (typeof window !== "undefined") window.localStorage.setItem("jimsai:active-thread", id);
  } catch {
    // ignore storage errors
  }
}

// Live SSE stream handle, kept outside React state so Stop can abort it.
let activeStream: AbortController | null = null;

// Build a full ApiResponse from the stream's `meta` event + accumulated text, so
// insights, badges, and feedback (trace_id) all work with the streamed answer.
function apiResponseFromMeta(
  meta: { trace_id?: string; confidence?: number; gaps?: string[]; sources?: string[]; used_llm?: boolean },
  text: string
): ApiResponse {
  const confidence = meta.confidence ?? 0;
  return {
    response: text,
    confidence,
    gaps: meta.gaps ?? [],
    sources: meta.sources ?? [],
    suggestions: [],
    used_groq: Boolean(meta.used_llm),
    used_llm: Boolean(meta.used_llm),
    ir: { trace_id: meta.trace_id ?? "", target_ir: "", confidence, transformer_interface_used: false },
    world_model_activations: [],
    simulation_results: [],
    trace: [],
    layer_results: [],
  };
}

interface ChatStore {
  // Thread / message state — online-first via backend API, no localStorage for data
  activeThreadId: string;
  threads: Thread[];
  messages: Record<string, Message[]>;
  threadsLoaded: boolean;
  messagesLoaded: Record<string, boolean>;

  // Drawer state
  drawerOpen: boolean;
  drawerMessageIndex: number | null;
  drawerTab: string;

  // Navigation state
  sidebarPanel: "threads" | "learn" | null;
  mobileNavOpen: boolean;

  // Query state
  loading: boolean;
  streaming: boolean;
  pendingEdit: string; // text to load into the composer (edit-prompt)
  feedbackStatus: string;
  learnedSignatureIds: Record<string, string>; // keyed by trace_id

  // Composer state
  canvasHint: boolean;
  inventionHint: boolean;

  // Sync actions
  setActiveThreadId: (id: string) => void;
  setThreads: (threads: Thread[]) => void;
  upsertThread: (thread: Thread) => void;
  removeThread: (id: string) => void;
  renameThread: (id: string, title: string) => void;
  setMessages: (threadId: string, messages: Message[]) => void;
  appendMessage: (threadId: string, message: Message) => void;
  replaceLastAssistantMessage: (threadId: string, message: Message) => void;
  openDrawer: (index: number, tab?: string) => void;
  closeDrawer: () => void;
  setDrawerTab: (tab: string) => void;
  setSidebarPanel: (panel: "threads" | "learn" | null) => void;
  setMobileNavOpen: (open: boolean) => void;
  setLoading: (v: boolean) => void;
  stopStreaming: () => void;
  setPendingEdit: (s: string) => void;
  setFeedbackStatus: (s: string) => void;
  storeLearned: (traceId: string, sigId: string) => void;
  removeLearned: (traceId: string) => void;
  setCanvasHint: (v: boolean) => void;
  setInventionHint: (v: boolean) => void;

  // Async data actions (all data from backend API)
  loadThreads: (apiBase: string, headers: Record<string, string>, userId: string, workspaceId?: string) => Promise<void>;
  loadMessages: (threadId: string, apiBase: string, headers: Record<string, string>, userId: string) => Promise<void>;
  sendQuery: (input: string, apiBase: string, headers: Record<string, string>, userId: string, workspaceId: string | undefined) => Promise<void>;
  submitFeedback: (rating: "positive" | "negative" | "correction", message: Message, notes: string, apiBase: string, headers: Record<string, string>, userId: string, workspaceId: string | undefined) => Promise<void>;
  learnResponse: (message: Message, apiBase: string, headers: Record<string, string>, userId: string, workspaceId: string | undefined) => Promise<string | null>;
  unlearnResponse: (traceId: string, apiBase: string, headers: Record<string, string>, userId: string, workspaceId: string | undefined) => Promise<void>;
  deleteThread: (threadId: string, apiBase: string, headers: Record<string, string>, userId: string) => Promise<void>;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  // Only activeThreadId persists locally — all other data comes from the backend
  activeThreadId: getStoredThreadId(),
  threads: [],
  messages: {},
  threadsLoaded: false,
  messagesLoaded: {},
  drawerOpen: false,
  drawerMessageIndex: null,
  drawerTab: "answer",
  sidebarPanel: null,
  mobileNavOpen: false,
  loading: false,
  streaming: false,
  pendingEdit: "",
  feedbackStatus: "",
  learnedSignatureIds: {},
  canvasHint: false,
  inventionHint: false,

  setActiveThreadId: (id) => { persistThreadId(id); set({ activeThreadId: id }); },
  setThreads: (threads) => set({ threads, threadsLoaded: true }),
  upsertThread: (thread) =>
    set((s) => {
      const exists = s.threads.find((t) => t.id === thread.id);
      return exists
        ? { threads: s.threads.map((t) => (t.id === thread.id ? { ...t, ...thread } : t)) }
        : { threads: [thread, ...s.threads] };
    }),
  removeThread: (id) => set((s) => ({ threads: s.threads.filter((t) => t.id !== id) })),
  renameThread: (id, title) =>
    set((s) => ({ threads: s.threads.map((t) => (t.id === id ? { ...t, title } : t)) })),
  setMessages: (threadId, messages) =>
    set((s) => ({
      messages: { ...s.messages, [threadId]: messages },
      messagesLoaded: { ...s.messagesLoaded, [threadId]: true },
    })),
  appendMessage: (threadId, message) =>
    set((s) => ({
      messages: { ...s.messages, [threadId]: [...(s.messages[threadId] ?? []), message] },
    })),
  replaceLastAssistantMessage: (threadId, message) =>
    set((s) => {
      const msgs = [...(s.messages[threadId] ?? [])];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant") {
          msgs[i] = message;
          break;
        }
      }
      return { messages: { ...s.messages, [threadId]: msgs } };
    }),
  openDrawer: (index, tab = "answer") =>
    set({ drawerOpen: true, drawerMessageIndex: index, drawerTab: tab }),
  closeDrawer: () => set({ drawerOpen: false }),
  setDrawerTab: (tab) => set({ drawerTab: tab }),
  setSidebarPanel: (panel) => set({ sidebarPanel: panel }),
  setMobileNavOpen: (open) => set({ mobileNavOpen: open }),
  setLoading: (v) => set({ loading: v }),
  stopStreaming: () => { activeStream?.abort(); },
  setPendingEdit: (s) => set({ pendingEdit: s }),
  setFeedbackStatus: (s) => set({ feedbackStatus: s }),
  storeLearned: (traceId, sigId) =>
    set((s) => ({ learnedSignatureIds: { ...s.learnedSignatureIds, [traceId]: sigId } })),
  removeLearned: (traceId) =>
    set((s) => {
      const n = { ...s.learnedSignatureIds };
      delete n[traceId];
      return { learnedSignatureIds: n };
    }),
  setCanvasHint: (v) => set({ canvasHint: v }),
  setInventionHint: (v) => set({ inventionHint: v }),

  // ── Async actions — all data from backend API ──────────────────────────

  loadThreads: async (apiBase, headers, userId, workspaceId) => {
    try {
      const params = new URLSearchParams({ user_id: userId, limit: "50" });
      if (workspaceId) params.set("workspace_id", workspaceId);
      const res = await fetch(`${apiBase}/v1/chat/threads?${params}`, { headers });
      if (!res.ok) return;
      const data = (await res.json()) as {
        threads: Array<{ id: string; title: string; updated_at?: string; created_at?: string }>;
      };
      get().setThreads(
        (data.threads ?? []).map((t) => ({
          id: t.id,
          title: t.title || "Untitled",
          updated_at: t.updated_at ?? t.created_at ?? new Date().toISOString(),
          created_at: t.created_at,
        }))
      );
    } catch {
      // silent failure — empty thread list shown, user can start new chat
    }
  },

  loadMessages: async (threadId, apiBase, headers, userId) => {
    if (get().messagesLoaded[threadId]) return;
    try {
      const params = new URLSearchParams({ user_id: userId, limit: "200" });
      const res = await fetch(
        `${apiBase}/v1/chat/threads/${encodeURIComponent(threadId)}/messages?${params}`,
        { headers }
      );
      if (!res.ok) return;
      const data = (await res.json()) as {
        messages: Array<{ role: "user" | "assistant"; content: string }>;
      };
      get().setMessages(
        threadId,
        (data.messages ?? []).map((m) => ({ role: m.role, content: m.content }))
      );
    } catch {
      // silent
    }
  },

  sendQuery: async (input, apiBase, headers, userId, workspaceId) => {
    const query = input.trim();
    if (!query) return;
    const { activeThreadId, canvasHint, inventionHint } = get();

    get().appendMessage(activeThreadId, { role: "user", content: query });

    // Auto-name thread on first user message
    const thread = get().threads.find((t) => t.id === activeThreadId);
    if (!thread || thread.title === "New chat" || !thread.title) {
      get().renameThread(activeThreadId, query.length > 48 ? `${query.slice(0, 45)}...` : query);
    }
    get().upsertThread({
      id: activeThreadId,
      title: get().threads.find((t) => t.id === activeThreadId)?.title ?? query.slice(0, 48),
      updated_at: new Date().toISOString(),
    });

    // Placeholder assistant message that fills token-by-token as the SSE arrives.
    get().appendMessage(activeThreadId, { role: "assistant", content: "" });
    const abort = new AbortController();
    activeStream = abort;
    set({ loading: true, streaming: true });

    let acc = "";
    let meta: Parameters<typeof apiResponseFromMeta>[0] | null = null;
    const flush = () =>
      get().replaceLastAssistantMessage(activeThreadId, {
        role: "assistant",
        content: acc,
        apiResponse: meta ? apiResponseFromMeta(meta, acc) : undefined,
      });

    try {
      const res = await fetch(`${apiBase}/v1/query/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        signal: abort.signal,
        body: JSON.stringify({
          user_id: userId,
          workspace_id: workspaceId,
          thread_id: activeThreadId,
          query,
          canvas_hint: canvasHint,
          invention_hint: inventionHint,
          return_trace: true,
        }),
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          let evt: Record<string, unknown>;
          try { evt = JSON.parse(line.slice(5).trim()); } catch { continue; }
          if (evt.type === "meta") {
            meta = evt as unknown as typeof meta;
            flush(); // surface first token area + badges as soon as verification lands
          } else if (evt.type === "token") {
            acc += String(evt.text ?? "");
            flush();
          } else if (evt.type === "done") {
            acc = String(evt.response ?? acc);
            flush();
          } else if (evt.type === "error") {
            throw new Error(String(evt.detail ?? "stream error"));
          }
        }
      }
      if (!acc) flush();
    } catch (err) {
      if ((err as { name?: string })?.name === "AbortError") {
        // User pressed Stop — keep whatever streamed so far, mark it.
        get().replaceLastAssistantMessage(activeThreadId, {
          role: "assistant",
          content: acc ? `${acc}\n\n_[stopped]_` : "_[stopped]_",
          apiResponse: meta ? apiResponseFromMeta(meta, acc) : undefined,
        });
      } else {
        get().replaceLastAssistantMessage(activeThreadId, {
          role: "assistant",
          content: `⚠️ ${err instanceof Error ? err.message : "Request failed."}`,
        });
      }
    } finally {
      activeStream = null;
      set({ loading: false, streaming: false });
    }
  },

  submitFeedback: async (rating, message, notes, apiBase, headers, userId, workspaceId) => {
    if (!message.apiResponse) return;
    try {
      await fetch(`${apiBase}/v1/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          user_id: userId,
          workspace_id: workspaceId,
          trace_id: message.apiResponse.ir.trace_id,
          rating,
          notes,
          thread_id: get().activeThreadId,
          source_signature_ids: message.apiResponse.sources ?? [],
        }),
      });
      get().setFeedbackStatus(`Feedback: ${rating}`);
    } catch {
      get().setFeedbackStatus("Feedback failed");
    }
  },

  learnResponse: async (message, apiBase, headers, userId, workspaceId) => {
    if (!message.apiResponse) return null;
    get().setFeedbackStatus("Learning…");
    try {
      const r = await fetch(`${apiBase}/v1/training/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          user_id: userId,
          workspace_id: workspaceId,
          content: message.content,
          modality: "text",
          source_trust: Math.min(0.98, Math.max(0.5, message.apiResponse.confidence)),
          domain_hint: "learn_this_user_confirmed",
        }),
      });
      if (!r.ok) throw new Error("ingest failed");
      const d = (await r.json()) as { signature?: { id?: string } };
      const sigId = d.signature?.id ?? null;

      // Record positive feedback with source_signature_ids
      await fetch(`${apiBase}/v1/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          user_id: userId,
          workspace_id: workspaceId,
          trace_id: message.apiResponse.ir.trace_id,
          rating: "positive",
          notes: "learn_this",
          thread_id: get().activeThreadId,
          source_signature_ids: message.apiResponse.sources ?? [],
        }),
      });

      if (sigId) get().storeLearned(message.apiResponse.ir.trace_id, sigId);
      get().setFeedbackStatus("Learned into memory");
      return sigId;
    } catch {
      get().setFeedbackStatus("Learning failed");
      return null;
    }
  },

  unlearnResponse: async (traceId, apiBase, headers, userId, workspaceId) => {
    const sigId = get().learnedSignatureIds[traceId];
    if (!sigId) return;
    try {
      await fetch(`${apiBase}/v1/memory/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          user_id: userId,
          workspace_id: workspaceId,
          signature_id: sigId,
          reason: "user_unlearn_response",
        }),
      });
      get().removeLearned(traceId);
      get().setFeedbackStatus("Unlearned from memory");
    } catch {
      get().setFeedbackStatus("Unlearn failed");
    }
  },

  deleteThread: async (threadId, apiBase, headers, userId) => {
    try {
      await fetch(`${apiBase}/v1/chat/threads/${encodeURIComponent(threadId)}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ user_id: userId }),
      });
    } catch {
      // silent — remove from store regardless
    }
    get().removeThread(threadId);
    if (get().activeThreadId === threadId) {
      const remaining = get().threads.filter((t) => t.id !== threadId);
      const nextId = remaining[0]?.id ?? createThreadId();
      if (!remaining.length) {
        get().upsertThread({ id: nextId, title: "New chat", updated_at: new Date().toISOString() });
      }
      get().setActiveThreadId(nextId);
    }
  },
}));
