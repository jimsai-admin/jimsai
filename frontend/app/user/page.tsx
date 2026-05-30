"use client";

import { ChangeEvent, FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BrainCircuit,
  BookOpenCheck,
  Download,
  GitBranch,
  Layers3,
  Lightbulb,
  ListTree,
  Paperclip,
  Send,
  ShieldCheck,
  Sparkles
} from "lucide-react";

import {
  clearSupabaseSession,
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

export default function UserConsole() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "JIMS-AI chat runtime ready. Ask with text, files, canvas, or invention routing." }
  ]);
  const [input, setInput] = useState("");
  const [memoryTrace, setMemoryTrace] = useState(true);
  const [reasoningTrace, setReasoningTrace] = useState(false);
  const [simulationTrace, setSimulationTrace] = useState(false);
  const [canvasHint, setCanvasHint] = useState(false);
  const [inventionHint, setInventionHint] = useState(false);
  const [insightsOpen, setInsightsOpen] = useState(true);
  const [last, setLast] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState("No feedback submitted.");
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
      const response = await fetch(`${apiBase}/v1/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          user_id: context.userId,
          workspace_id: context.workspaceId,
          query,
          canvas_hint: canvasHint,
          invention_hint: inventionHint,
          return_trace: true
        })
      });
      if (!response.ok) throw new Error(`query failed with HTTP ${response.status}`);
      const data = (await response.json()) as ApiResponse;
      setLast(data);
      setMessages((current) => [...current, { role: "assistant", content: data.response }]);
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
      body: JSON.stringify({ user_id: context.userId, trace_id: last.ir.trace_id, rating, notes })
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
              {message.content}
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
