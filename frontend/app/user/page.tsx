"use client";

import { ChangeEvent, FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BrainCircuit,
  BookOpenCheck,
  Check,
  Clipboard,
  Download,
  GitBranch,
  History,
  Layers3,
  Lightbulb,
  ListTree,
  Paperclip,
  Plus,
  Send,
  ShieldCheck,
  Sparkles
} from "lucide-react";

import {
  clearSupabaseSession,
  refreshSupabaseSession,
  storeSupabaseSession,
  supabaseAuthHeaders,
  supabaseUserContext
} from "../authHeaders";

type TraceEvent = { stage: string; message: string; data: Record<string, unknown> };
type LayerResult = { layer: string; activated: boolean; deterministic: boolean; summary: string; data: Record<string, unknown> };
type CapabilityPlan = {
  kind: string;
  route: string;
  confidence: number;
  reason: string;
  energy_profile: string;
  context_strategy: string;
  requires_external_adapter: boolean;
};
type CapabilityResult = { adapter: string; status: string; summary: string; confidence: number };
type ApiResponse = {
  response: string;
  confidence: number;
  gaps: string[];
  sources: string[];
  used_groq: boolean;
  ir: { trace_id: string; target_ir: string; confidence: number; transformer_interface_used: boolean };
  activation?: { route: string; reason: string; confidence: number };
  canvas_result?: { activated: boolean; patterns: string[]; used_groq: boolean };
  invention_result?: { activated: boolean; candidate_steps: string[]; simulation_notes: string[]; used_groq: boolean };
  abstraction_result?: { concepts: string[]; analogies: string[]; confidence: number };
  capability_plan?: CapabilityPlan;
  capability_results?: CapabilityResult[];
  world_model_activations: Array<{ rule: string; confidence: number; source: string }>;
  simulation_results: Array<{ scenario: string; passed: boolean; confidence: number; outcomes: string[] }>;
  trace: TraceEvent[];
  layer_results: LayerResult[];
};
type Message = { role: "user" | "assistant"; content: string };
type StoredThread = { id: string; title: string; updatedAt: string };
type ThreadResponse = {
  threads: Array<{ id: string; title: string; updated_at?: string; created_at?: string }>;
};
type MessageResponse = {
  messages: Array<{ role: "user" | "assistant"; content: string }>;
};

const initialAssistantMessage: Message = {
  role: "assistant",
  content: "JIMS-AI chat runtime ready. Ask with text, files, canvas, or invention routing."
};

function createThreadId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `thread_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function loadStoredThreads(): StoredThread[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem("jimsai:chat:threads") ?? "[]") as StoredThread[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function UserConsole() {
  const [threadId, setThreadId] = useState(() => {
    if (typeof window === "undefined") return "default";
    return window.localStorage.getItem("jimsai:chat:active-thread") || createThreadId();
  });
  const [threads, setThreads] = useState<StoredThread[]>(() => {
    const stored = loadStoredThreads();
    if (stored.length) return stored;
    return [{ id: threadId, title: "New thread", updatedAt: new Date().toISOString() }];
  });
  const [messages, setMessages] = useState<Message[]>([initialAssistantMessage]);
  const [input, setInput] = useState("");
  const [memoryTrace, setMemoryTrace] = useState(true);
  const [reasoningTrace, setReasoningTrace] = useState(false);
  const [simulationTrace, setSimulationTrace] = useState(false);
  const [canvasHint, setCanvasHint] = useState(false);
  const [inventionHint, setInventionHint] = useState(false);
  const [insightsOpen, setInsightsOpen] = useState(false);
  const [last, setLast] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState("No feedback submitted.");
  const [learnedSignatureId, setLearnedSignatureId] = useState<string | null>(null);
  const [authContext, setAuthContext] = useState(() => supabaseUserContext());
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authStatus, setAuthStatus] = useState(authContext.authenticated ? "Signed in." : "Sign in to query or train.");
  const [authConfigured, setAuthConfigured] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [backendStatus, setBackendStatus] = useState("Checking runtime.");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const apiBase = useMemo(() => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000", []);

  const authHeaders = useCallback((): Record<string, string> => {
    return supabaseAuthHeaders();
  }, []);

  const fetchWithNetworkRetry = useCallback(async (url: string, init: RequestInit) => {
    try {
      return await fetch(url, init);
    } catch (error) {
      await wait(750);
      try {
        return await fetch(url, init);
      } catch {
        await wait(1500);
        return await fetch(url, init);
      }
    }
  }, []);

  const resizeComposer = useCallback((node?: HTMLTextAreaElement | null) => {
    const target = node ?? textareaRef.current;
    if (!target) return;
    target.style.height = "auto";
    target.style.height = `${Math.min(target.scrollHeight, 220)}px`;
  }, []);

  function updateInput(value: string, node?: HTMLTextAreaElement | null) {
    setInput(value);
    requestAnimationFrame(() => resizeComposer(node));
  }

  function clearComposer() {
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.value = "";
      textareaRef.current.style.height = "auto";
    }
  }

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("jimsai:chat:active-thread", threadId);
    const stored = window.localStorage.getItem(`jimsai:chat:thread:${threadId}:messages`);
    if (!stored) {
      setMessages([initialAssistantMessage]);
      return;
    }
    try {
      const parsed = JSON.parse(stored) as Message[];
      setMessages(Array.isArray(parsed) && parsed.length ? parsed : [initialAssistantMessage]);
    } catch {
      setMessages([initialAssistantMessage]);
    }
  }, [threadId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("jimsai:chat:threads", JSON.stringify(threads));
  }, [threads]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(`jimsai:chat:thread:${threadId}:messages`, JSON.stringify(messages));
  }, [messages, threadId]);

  const loadRemoteThreads = useCallback(async () => {
    const context = supabaseUserContext();
    if (!context.authenticated) return;
    const params = new URLSearchParams({ user_id: context.userId, limit: "50" });
    if (context.workspaceId) params.set("workspace_id", context.workspaceId);
    let response = await fetchWithNetworkRetry(`${apiBase}/v1/chat/threads?${params.toString()}`, {
      headers: authHeaders()
    });
    if (response.status === 401 && await refreshSupabaseSession(apiBase)) {
      response = await fetchWithNetworkRetry(`${apiBase}/v1/chat/threads?${params.toString()}`, {
        headers: authHeaders()
      });
    }
    if (!response.ok) return;
    const data = (await response.json()) as ThreadResponse;
    if (!data.threads.length) return;
    const remoteThreads = data.threads.map((thread) => ({
      id: thread.id,
      title: thread.title || "Untitled thread",
      updatedAt: thread.updated_at ?? thread.created_at ?? new Date().toISOString()
    }));
    setThreads((current) => {
      const currentById = new Map(current.map((thread) => [thread.id, thread]));
      for (const thread of remoteThreads) currentById.set(thread.id, thread);
      return Array.from(currentById.values())
        .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
        .slice(0, 50);
    });
  }, [apiBase, authHeaders, fetchWithNetworkRetry]);

  const loadRemoteMessages = useCallback(async (nextThreadId: string) => {
    const context = supabaseUserContext();
    if (!context.authenticated || !nextThreadId) return;
    const params = new URLSearchParams({ user_id: context.userId, limit: "200" });
    let response = await fetchWithNetworkRetry(`${apiBase}/v1/chat/threads/${encodeURIComponent(nextThreadId)}/messages?${params.toString()}`, {
      headers: authHeaders()
    });
    if (response.status === 401 && await refreshSupabaseSession(apiBase)) {
      response = await fetchWithNetworkRetry(`${apiBase}/v1/chat/threads/${encodeURIComponent(nextThreadId)}/messages?${params.toString()}`, {
        headers: authHeaders()
      });
    }
    if (!response.ok) return;
    const data = (await response.json()) as MessageResponse;
    if (data.messages.length) {
      setMessages(data.messages.map((message) => ({ role: message.role, content: message.content })));
    }
  }, [apiBase, authHeaders, fetchWithNetworkRetry]);

  useEffect(() => {
    if (authContext.authenticated) void loadRemoteThreads();
  }, [authContext.authenticated, loadRemoteThreads]);

  useEffect(() => {
    if (authContext.authenticated) void loadRemoteMessages(threadId);
  }, [authContext.authenticated, loadRemoteMessages, threadId]);

  useEffect(() => {
    function toggleInsights() {
      setInsightsOpen((open) => !open);
    }

    window.addEventListener("jimsai:toggle-insights", toggleInsights);
    return () => window.removeEventListener("jimsai:toggle-insights", toggleInsights);
  }, []);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("jimsai:insights-state", { detail: { open: insightsOpen } }));
  }, [insightsOpen]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiBase}/health`)
      .then(async (response) => {
        if (cancelled) return;
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as { status?: string; architecture?: string };
        setBackendStatus(data.status === "ok" ? "Runtime ready" : "Runtime reachable");
      })
      .catch((error) => {
        if (!cancelled) setBackendStatus(error instanceof Error ? `Runtime check failed: ${error.message}` : "Runtime check failed");
      });
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiBase}/v1/auth/config`)
      .then(async (response) => {
        if (cancelled) return;
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as { configured?: boolean };
        setAuthConfigured(Boolean(data.configured));
        if (!data.configured) setAuthStatus("Supabase auth is not configured on the backend.");
      })
      .catch((error) => {
        if (!cancelled) {
          setAuthConfigured(false);
          setAuthStatus(error instanceof Error ? `Auth config unavailable: ${error.message}` : "Auth config unavailable.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || loading) return;
    const query = input.trim();
    clearComposer();
    const context = supabaseUserContext();
    setAuthContext(context);
    if (!context.authenticated) {
      setMessages((current) => [...current, { role: "assistant", content: "Sign in with Supabase before querying the protected runtime." }]);
      return;
    }
    setMessages((current) => [...current, { role: "user", content: query }]);
    setLoading(true);
    try {
      let response = await fetchWithNetworkRetry(`${apiBase}/v1/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          user_id: context.userId,
          workspace_id: context.workspaceId,
          thread_id: threadId,
          query,
          canvas_hint: canvasHint,
          invention_hint: inventionHint,
          return_trace: true
        })
      });
      if (response.status === 401 && await refreshSupabaseSession(apiBase)) {
        response = await fetchWithNetworkRetry(`${apiBase}/v1/query`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({
            user_id: context.userId,
            workspace_id: context.workspaceId,
            thread_id: threadId,
            query,
            canvas_hint: canvasHint,
            invention_hint: inventionHint,
            return_trace: true
          })
        });
      }
      if (response.status === 401) {
        clearSupabaseSession();
        setAuthContext(supabaseUserContext());
        throw new Error("session expired; sign in again");
      }
      if (!response.ok) throw new Error(`query failed with HTTP ${response.status}`);
      const data = (await response.json()) as ApiResponse;
      setLast(data);
      setLearnedSignatureId(null);
      setMessages((current) => [...current, { role: "assistant", content: data.response }]);
      setThreads((current) => {
        const title = query.length > 48 ? `${query.slice(0, 45)}...` : query;
        const updatedAt = new Date().toISOString();
        const existing = current.filter((thread) => thread.id !== threadId);
        return [{ id: threadId, title, updatedAt }, ...existing].slice(0, 20);
      });
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", content: error instanceof Error ? `API request failed: ${error.message}` : "API request failed." }]);
    } finally {
      setLoading(false);
    }
  }

  async function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    updateInput(`${input}\n\n${text}`.trim());
    event.target.value = "";
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  async function submitFeedback(rating: "positive" | "negative" | "correction", notes: string) {
    if (!last) return;
    const context = supabaseUserContext();
    const response = await fetch(`${apiBase}/v1/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        user_id: context.userId,
        workspace_id: context.workspaceId,
        trace_id: last.ir.trace_id,
        rating,
        notes,
        thread_id: threadId
      })
    });
    if (!response.ok) {
      setFeedbackStatus("feedback rejected");
      return;
    }
    const data = (await response.json()) as { accepted: boolean; stored_events: number };
    setFeedbackStatus(data.accepted ? `feedback stored (${data.stored_events})` : "feedback rejected");
  }

  async function learnCurrentAnswer() {
    if (!last) return;
    const context = supabaseUserContext();
    setFeedbackStatus("learning response");
    try {
      const response = await fetch(`${apiBase}/v1/training/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          user_id: context.userId,
          workspace_id: context.workspaceId,
          content: last.response,
          modality: "text",
          source_trust: Math.max(0.5, Math.min(last.confidence, 0.98)),
          domain_hint: "learn_this_user_confirmed"
        })
      });
      if (!response.ok) throw new Error("learn failed");
      const data = (await response.json()) as { signature?: { id?: string } };
      setLearnedSignatureId(data.signature?.id ?? null);
      await submitFeedback("positive", "learn_this");
      setFeedbackStatus("learned into memory");
    } catch {
      setFeedbackStatus("learning failed");
    }
  }

  async function authenticate(mode: "signin" | "signup") {
    if (!authConfigured || !email.trim() || !password) return;
    setAuthBusy(true);
    setAuthStatus(mode === "signin" ? "Signing in." : "Creating account.");
    try {
      const response = await fetch(`${apiBase}/v1/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password })
      });
      const data = (await response.json()) as Record<string, unknown>;
      if (!response.ok) throw new Error(String(data.detail ?? data.msg ?? data.error_description ?? data.error ?? "auth failed"));
      storeSupabaseSession(data);
      const context = supabaseUserContext();
      setAuthContext(context);
      setAuthStatus(context.authenticated ? "Signed in." : "Account created. Confirm email if Supabase requires it, then sign in.");
    } catch (error) {
      setAuthStatus(error instanceof Error ? error.message : "Authentication failed.");
    } finally {
      setAuthBusy(false);
    }
  }

  function signOut() {
    clearSupabaseSession();
    const context = supabaseUserContext();
    setAuthContext(context);
    setAuthStatus("Signed out.");
  }

  function startNewThread() {
    const nextThreadId = createThreadId();
    setThreads((current) => [{ id: nextThreadId, title: "New thread", updatedAt: new Date().toISOString() }, ...current].slice(0, 20));
    setThreadId(nextThreadId);
    setLast(null);
    setLearnedSignatureId(null);
    setFeedbackStatus("No feedback submitted.");
  }

  async function deleteCurrentThread() {
    const context = supabaseUserContext();
    if (!context.authenticated || !threadId) return;
    if (!window.confirm("Delete this chat thread from your local UI and production history?")) return;
    await fetch(`${apiBase}/v1/chat/threads/${encodeURIComponent(threadId)}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ user_id: context.userId })
    }).catch(() => null);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(`jimsai:chat:thread:${threadId}:messages`);
    }
    const remaining = threads.filter((thread) => thread.id !== threadId);
    const next = remaining[0]?.id ?? createThreadId();
    setThreads(remaining.length ? remaining : [{ id: next, title: "New thread", updatedAt: new Date().toISOString() }]);
    setThreadId(next);
    setLast(null);
    setLearnedSignatureId(null);
  }

  async function unlearnCurrentAnswer() {
    const context = supabaseUserContext();
    if (!learnedSignatureId) {
      setFeedbackStatus("No learned memory selected to unlearn.");
      return;
    }
    const response = await fetch(`${apiBase}/v1/memory/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        user_id: context.userId,
        workspace_id: context.workspaceId,
        signature_id: learnedSignatureId,
        reason: "user_unlearn_current_answer"
      })
    });
    if (!response.ok) {
      setFeedbackStatus("unlearn failed");
      return;
    }
    await submitFeedback("correction", `unlearn:${learnedSignatureId}`);
    setLearnedSignatureId(null);
    setFeedbackStatus("unlearned memory");
  }

  function exportReasoning() {
    if (!last) return;
    const blob = new Blob([JSON.stringify({ trace_id: last.ir.trace_id, layer_results: last.layer_results, trace: last.trace, sources: last.sources, gaps: last.gaps }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `jimsai-reasoning-${last.ir.trace_id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (!authContext.authenticated) {
    return (
      <main className="authShell">
        <section className="authCard">
          <div>
            <p className="eyebrow">Workspace Access</p>
            <h1>Sign in to JIMS-AI</h1>
            <p>Protected chat, training, feedback, and memory writes require a workspace identity.</p>
          </div>
          <div className="authForm">
            <label>
              Email
              <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" />
            </label>
            <label>
              Password
              <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" />
            </label>
            <div className="buttonRow">
              <button className="sendButton" type="button" disabled={authBusy || !authConfigured} onClick={() => authenticate("signin")}>Sign in</button>
              <button className="iconTextButton" type="button" disabled={authBusy || !authConfigured} onClick={() => authenticate("signup")}>Create account</button>
            </div>
            <div className="authMeta">
              <span>{authStatus}</span>
              <span>{backendStatus}</span>
              {!authConfigured ? <span>Backend auth config is unavailable.</span> : null}
            </div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className={`workspace chatWorkspace ${insightsOpen ? "" : "insightsCollapsed"}`}>
      <section className="workbench chatWorkbench">
        <div className="messages">
          {messages.map((message, index) => (
            <article className={`message ${message.role === "user" ? "user" : ""}`} key={`${message.role}-${index}`}>
              <span className="messageRole">{message.role === "user" ? "You" : "JIMS-AI"}</span>
              <MarkdownMessage content={message.content} />
            </article>
          ))}
        </div>

        <form className="composer" onSubmit={submit}>
          <input ref={fileInputRef} type="file" hidden onChange={handleFileSelected} />
          <button className="iconButton" type="button" title="Attach file" onClick={() => fileInputRef.current?.click()}>
            <Paperclip size={18} />
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            rows={1}
            onChange={(event) => updateInput(event.target.value, event.currentTarget)}
            onKeyDown={handleComposerKeyDown}
            placeholder="Ask about stored memory, source-backed claims, causal paths, code impact, files, or invention routing."
            aria-label="Prompt input"
          />
          <div className="composerActions">
            <button className={`iconButton ${canvasHint ? "active" : ""}`} type="button" title="Canvas route" onClick={() => setCanvasHint((value) => !value)}>
              <GitBranch size={18} />
            </button>
            <button className={`iconButton ${inventionHint ? "active" : ""}`} type="button" title="Invention route" onClick={() => setInventionHint((value) => !value)}>
              <Lightbulb size={18} />
            </button>
            <button className="sendButton" type="submit" disabled={loading}>
              <Send size={18} /><span>{loading ? "Running" : "Send"}</span>
            </button>
          </div>
        </form>
      </section>

      <aside className="sideRail insightRail">
        <div className="insightRailHeader">
          <div>
            <span className="recordKind">Verified runtime</span>
            <strong>Sources, gaps, and layer state</strong>
          </div>
          <button className="iconTextButton" type="button" onClick={signOut}>Sign out</button>
        </div>

        <section className="panel threadPanel">
          <h2><History size={15} /> Threads</h2>
          <div className="threadControls">
            <select value={threadId} onChange={(event) => setThreadId(event.target.value)} aria-label="Chat thread">
              {threads.map((thread) => (
                <option value={thread.id} key={thread.id}>{thread.title}</option>
              ))}
            </select>
            <button className="iconButton" type="button" title="New thread" onClick={startNewThread}>
              <Plus size={16} />
            </button>
            <button className="iconTextButton compact danger" type="button" onClick={deleteCurrentThread}>
              Delete
            </button>
          </div>
        </section>

        <section className="panel evidenceSummary">
          <h2><ShieldCheck size={15} /> Answer State</h2>
          <div className="metricGrid compact">
            <div className="metric">
              <strong>{last ? last.confidence.toFixed(2) : "n/a"}</strong>
              <span>confidence</span>
            </div>
            <div className="metric">
              <strong>{last?.sources.length ?? 0}</strong>
              <span>sources</span>
            </div>
            <div className="metric">
              <strong>{last?.gaps.length ?? 0}</strong>
              <span>gaps</span>
            </div>
            <div className="metric">
              <strong>{last?.capability_plan?.kind ?? "n/a"}</strong>
              <span>capability</span>
            </div>
          </div>
          <div className="traceToggles">
            <label className="toggle">Sources <input type="checkbox" checked={memoryTrace} onChange={(event) => setMemoryTrace(event.target.checked)} /></label>
            <label className="toggle">Reasoning <input type="checkbox" checked={reasoningTrace} onChange={(event) => setReasoningTrace(event.target.checked)} /></label>
            <label className="toggle">Simulation <input type="checkbox" checked={simulationTrace} onChange={(event) => setSimulationTrace(event.target.checked)} /></label>
          </div>
        </section>

        {reasoningTrace ? <section className="panel">
          <h2><Layers3 size={15} /> Layer Chain</h2>
          <div className="traceList">
            {last?.layer_results.map((layer) => (
              <div className="layerRow" key={layer.layer}>
                <span className={layer.activated ? "state on" : "state"} />
                <div>
                  <strong>{layer.layer}</strong>
                  <small>{layer.deterministic ? "deterministic" : "bounded Groq"}</small>
                </div>
              </div>
            )) ?? <div className="muted">No execution trace yet.</div>}
          </div>
        </section> : null}

        <section className="panel">
          <h2><Sparkles size={15} /> Capability</h2>
          {last?.capability_plan ? (
            <div className="traceList">
              <div className="traceItem">
                <strong>{last.capability_plan.kind}</strong>
                <span>{last.capability_plan.route} / {last.capability_plan.context_strategy} / energy {last.capability_plan.energy_profile}</span>
                <span>{last.capability_plan.reason}</span>
              </div>
              {last.capability_results?.map((result) => (
                <div className="traceItem" key={`${result.adapter}-${result.status}`}>
                  <strong>{result.status}</strong>
                  <span>{result.adapter}</span>
                  <span>{result.summary}</span>
                </div>
              ))}
            </div>
          ) : <div className="muted">No capability route yet.</div>}
        </section>

        {reasoningTrace && last?.abstraction_result?.concepts?.length ? <section className="panel">
          <h2><Sparkles size={15} /> Abstraction</h2>
          <div className="pillGroup">
            {last?.abstraction_result?.concepts?.length ? last.abstraction_result.concepts.map((concept) => <span className="pill" key={concept}>{concept}</span>) : <span className="muted">No concepts yet.</span>}
          </div>
        </section> : null}

        {reasoningTrace || last?.world_model_activations?.length ? <section className="panel">
          <h2><BrainCircuit size={15} /> World Model</h2>
          <div className="traceList">
            {last?.world_model_activations?.length ? last.world_model_activations.map((rule) => (
              <div className="traceItem" key={`${rule.source}-${rule.rule}`}>{rule.rule} ({rule.confidence.toFixed(2)})</div>
            )) : <div className="muted">No causal rules activated.</div>}
          </div>
        </section> : null}

        <section className="panel">
          <h2><ShieldCheck size={15} /> Sources</h2>
          <div className="pillGroup">
            {memoryTrace && last?.sources.length ? last.sources.map((source) => <span className="pill" key={source}>{source}</span>) : <span className="muted">No source signatures yet.</span>}
          </div>
        </section>

        {simulationTrace ? <section className="panel">
          <h2><ListTree size={15} /> Simulation</h2>
          <div className="traceList">
            {simulationTrace && last?.simulation_results.map((sim) => (
              <div className="traceItem" key={sim.scenario}>
                <strong>{sim.scenario}</strong>
                <span>{sim.passed ? "passed" : "failed"} at {sim.confidence.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </section> : null}

        <section className={`panel ${last?.gaps.length ? "gapPanel" : ""}`}>
          <h2><AlertTriangle size={15} /> Gaps</h2>
          <div className="traceList">
            {last?.gaps.length ? last.gaps.map((gap) => <div className="traceItem" key={gap}>{gap}</div>) : <div className="muted">No explicit gaps reported.</div>}
          </div>
        </section>

        <section className="panel">
          <h2>Memory Controls</h2>
          <div className="buttonRow">
            <button className="sendButton" type="button" disabled={!last} onClick={learnCurrentAnswer}><BookOpenCheck size={16} /> Learn This</button>
            <button className="iconTextButton" type="button" disabled={!learnedSignatureId} onClick={unlearnCurrentAnswer}>Unlearn</button>
            <button className="iconTextButton" type="button" disabled={!last} onClick={exportReasoning}><Download size={16} /> Export Trace</button>
          </div>
          <div className="muted">{feedbackStatus}</div>
        </section>

        {reasoningTrace ? <section className="panel">
          <h2>Execution Trace</h2>
          <div className="traceList">
            {reasoningTrace && last?.trace.map((event, index) => (
              <div className="traceItem" key={`${event.stage}-${index}`}>
                <strong>{event.stage}</strong>
                <span>{event.message}</span>
              </div>
            ))}
          </div>
        </section> : null}
      </aside>

    </main>
  );
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function MarkdownMessage({ content }: { content: string }) {
  const blocks = useMemo(() => parseMarkdownBlocks(content), [content]);
  return (
    <div className="markdownMessage">
      {blocks.map((block, index) => {
        if (block.type === "code") {
          return <CodeBlock code={block.content} language={block.language} key={`code-${index}`} />;
        }
        return <MarkdownText text={block.content} key={`text-${index}`} />;
      })}
    </div>
  );
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <div className="codeBlock">
      <div className="codeBlockHeader">
        <span>{language || "code"}</span>
        <button className="codeCopyButton" type="button" onClick={copyCode}>
          {copied ? <Check size={14} /> : <Clipboard size={14} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

function MarkdownText({ text }: { text: string }) {
  const lines = text.split(/\n+/).filter((line) => line.trim().length > 0);
  return (
    <>
      {lines.map((line, index) => {
        const trimmed = line.trim();
        if (/^#{1,3}\s+/.test(trimmed)) {
          const level = trimmed.match(/^#+/)?.[0].length ?? 2;
          const Tag = level === 1 ? "h1" : level === 2 ? "h2" : "h3";
          return <Tag key={`${trimmed}-${index}`}>{renderInlineMarkdown(trimmed.replace(/^#{1,3}\s+/, ""))}</Tag>;
        }
        if (/^[-*]\s+/.test(trimmed)) {
          return <p className="markdownListItem" key={`${trimmed}-${index}`}>{renderInlineMarkdown(trimmed.replace(/^[-*]\s+/, ""))}</p>;
        }
        return <p key={`${trimmed}-${index}`}>{renderInlineMarkdown(trimmed)}</p>;
      })}
    </>
  );
}

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function parseMarkdownBlocks(content: string): Array<{ type: "text" | "code"; content: string; language: string }> {
  const blocks: Array<{ type: "text" | "code"; content: string; language: string }> = [];
  const fencePattern = /```(\w+)?\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = fencePattern.exec(content)) !== null) {
    if (match.index > lastIndex) {
      blocks.push({ type: "text", content: content.slice(lastIndex, match.index), language: "" });
    }
    blocks.push({ type: "code", language: match[1] ?? "", content: match[2].replace(/\n$/, "") });
    lastIndex = fencePattern.lastIndex;
  }
  if (lastIndex < content.length) {
    blocks.push({ type: "text", content: content.slice(lastIndex), language: "" });
  }
  return blocks.length ? blocks : [{ type: "text", content, language: "" }];
}
