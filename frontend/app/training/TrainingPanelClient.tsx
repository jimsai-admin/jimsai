"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChangeEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  Bot,
  Check,
  ClipboardCheck,
  Cpu,
  Database,
  FileUp,
  GitBranch,
  HardDriveUpload,
  History,
  ListChecks,
  PackageCheck,
  Pencil,
  RefreshCw,
  RotateCcw,
  Route,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  X
} from "lucide-react";

import { refreshSupabaseSession, supabaseAuthHeaders, supabaseUserContext } from "../authHeaders";
import { panelById, panelDefinitions, TrainingPanelId } from "./panels";

type TrainingPanelItem = {
  id: string;
  panel: string;
  kind: string;
  title: string;
  subtitle: string;
  data: Record<string, unknown>;
  created_at: string;
};

type TrainingPanelPage = {
  panel: string;
  items: TrainingPanelItem[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
};

type IngestResponse = {
  signature: { id: string };
  sppe_training_pair: { accepted: boolean };
};

type KaggleRunResponse = {
  run_id: string;
  status: string;
  task_type: string;
  kernel_ref: string | null;
  local_path: string | null;
  detail: string;
};

type RecordAction =
  | { type: "delete-memory"; signatureId: string }
  | { type: "update-memory"; signatureId: string; currentContent: string }
  | { type: "review"; action: "accept" | "correct" | "reject" | "promote" | "rollback"; provenance: string; rule: string }
  | { type: "sync-kaggle"; runId: string }
  | { type: "replay-canvas" }
  | { type: "replay-invention"; goal: string; domain: string };

const panelIcons: Record<TrainingPanelId, ReactNode> = {
  ingestion: <HardDriveUpload size={16} />,
  review: <ClipboardCheck size={16} />,
  ambiguity: <SlidersHorizontal size={16} />,
  memory: <Database size={16} />,
  "world-model": <GitBranch size={16} />,
  pipeline: <ListChecks size={16} />,
  sessions: <History size={16} />,
  feedback: <ShieldCheck size={16} />,
  autonomous: <Bot size={16} />,
  artifacts: <PackageCheck size={16} />,
  evaluation: <BarChart3 size={16} />
};

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export default function TrainingPanelClient({ panelId }: { panelId: string }) {
  const panel = panelById(panelId);
  const [items, setItems] = useState<TrainingPanelItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("");
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [domainHint, setDomainHint] = useState("workspace_training");
  const [sourceTrust, setSourceTrust] = useState(0.92);
  const [modality, setModality] = useState("text");
  const [status, setStatus] = useState("Ready.");
  const apiBase = useMemo(() => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000", []);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const trainingTextRef = useRef<HTMLTextAreaElement | null>(null);
  const loadingRef = useRef(false);
  const requestSeqRef = useRef(0);
  const activePanelRef = useRef(panelId);
  const router = useRouter();

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

  const routeToSignIn = useCallback((message = "Session expired. Sign in again to load protected training panels.") => {
    setStatus(message);
    setItems([]);
    setNextCursor(null);
    setHasMore(false);
    setTotal(0);
    router.replace("/user");
  }, [router]);

  const fetchPage = useCallback(
    async (cursor: string | null, replace = false) => {
      if (loadingRef.current && !replace) return;
      if (!supabaseUserContext().authenticated) {
        routeToSignIn("Sign in from Chat to load protected training panels.");
        return;
      }
      const requestedPanel = panelId;
      const requestId = ++requestSeqRef.current;
      loadingRef.current = true;
      setLoading(true);
      setLoadingLabel(replace ? `Loading ${panel.title}.` : "Loading more records.");
      try {
        const params = new URLSearchParams({ limit: "20" });
        if (cursor) params.set("cursor", cursor);
        let response = await fetchWithNetworkRetry(`${apiBase}/v1/training/panels/${requestedPanel}/items?${params.toString()}`, {
          headers: authHeaders()
        });
        if (response.status === 401 && await refreshSupabaseSession(apiBase)) {
          response = await fetchWithNetworkRetry(`${apiBase}/v1/training/panels/${requestedPanel}/items?${params.toString()}`, {
            headers: authHeaders()
          });
        }
        if (response.status === 401) {
          routeToSignIn();
          return;
        }
        if (!response.ok) throw new Error(`panel request failed with HTTP ${response.status}`);
        const page = (await response.json()) as TrainingPanelPage;
        if (requestId !== requestSeqRef.current || activePanelRef.current !== requestedPanel || page.panel !== requestedPanel) return;
        setItems((current) => (replace ? page.items : [...current, ...page.items]));
        setNextCursor(page.next_cursor);
        setHasMore(page.has_more);
        setTotal(page.total);
        setStatus(page.total ? `Loaded ${page.total} ${panel.title.toLowerCase()} records.` : `No ${panel.title.toLowerCase()} records yet.`);
      } catch (error) {
        if (requestId !== requestSeqRef.current || activePanelRef.current !== requestedPanel) return;
        setStatus(error instanceof Error ? `Panel request failed: ${error.message}` : "Panel request failed.");
        if (replace) {
          setItems([]);
          setNextCursor(null);
          setHasMore(false);
          setTotal(0);
        }
      } finally {
        if (requestId === requestSeqRef.current) {
          loadingRef.current = false;
          setLoading(false);
          setLoadingLabel("");
        }
      }
    },
    [apiBase, authHeaders, fetchWithNetworkRetry, panel.title, panelId, routeToSignIn]
  );

  useEffect(() => {
    activePanelRef.current = panelId;
    requestSeqRef.current += 1;
    loadingRef.current = false;
    setLoading(false);
    setLoadingLabel("");
    setItems([]);
    setNextCursor(null);
    setHasMore(true);
    setTotal(0);
    setStatus(`Loading ${panel.title}.`);
    void fetchPage(null, true);
  }, [fetchPage, panel.title, panelId]);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && hasMore && nextCursor && !loadingRef.current) {
        void fetchPage(nextCursor, false);
      }
    }, { rootMargin: "280px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, [fetchPage, hasMore, nextCursor]);

  async function refresh() {
    await fetchPage(null, true);
  }

  async function authedFetch(path: string, init: RequestInit = {}) {
    const headers = {
      ...(init.headers as Record<string, string> | undefined),
      ...authHeaders()
    };
    let response = await fetch(`${apiBase}${path}`, { ...init, headers });
    if (response.status === 401 && await refreshSupabaseSession(apiBase)) {
      response = await fetch(`${apiBase}${path}`, { ...init, headers: { ...(init.headers as Record<string, string> | undefined), ...authHeaders() } });
    }
    if (response.status === 401) routeToSignIn();
    return response;
  }

  async function handleRecordAction(action: RecordAction) {
    const context = supabaseUserContext();
    const actionKey = `${action.type}:${"signatureId" in action ? action.signatureId : "rule" in action ? action.rule : "runId" in action ? action.runId : "session"}`;
    setActionBusy(actionKey);
    try {
      if (action.type === "delete-memory") {
        if (!window.confirm("Delete this memory signature, graph edges, candidates, and cached results?")) return;
        setStatus("Deleting memory signature.");
        const response = await authedFetch("/v1/memory/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: context.userId, workspace_id: context.workspaceId, signature_id: action.signatureId, reason: "training_panel_delete" })
        });
        if (!response.ok) throw new Error(`delete failed with HTTP ${response.status}`);
        setStatus("Memory signature deleted.");
      } else if (action.type === "update-memory") {
        const corrected = window.prompt("Correct this memory record:", action.currentContent);
        if (corrected === null) return;
        if (!corrected.trim()) {
          setStatus("Correction is empty; update skipped.");
          return;
        }
        setStatus("Updating memory signature.");
        const response = await authedFetch("/v1/memory/update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: context.userId,
            workspace_id: context.workspaceId,
            signature_id: action.signatureId,
            corrected_content: corrected,
            source_trust: sourceTrust,
            domain_hint: domainHint,
            notes: "training_panel_update"
          })
        });
        if (!response.ok) throw new Error(`update failed with HTTP ${response.status}`);
        setStatus("Memory signature updated.");
      } else if (action.type === "review") {
        const correctedRule = action.action === "correct" ? window.prompt("Correct this world-model rule:", action.rule) : null;
        if (action.action === "correct" && (!correctedRule || !correctedRule.trim())) {
          setStatus("Correction is empty; review update skipped.");
          return;
        }
        setStatus(`${action.action} review action running.`);
        const response = await authedFetch("/v1/review/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: context.userId,
            provenance: action.provenance,
            rule: action.rule,
            action: action.action,
            corrected_rule: correctedRule,
            notes: `training_panel_${action.action}`
          })
        });
        if (!response.ok) throw new Error(`review failed with HTTP ${response.status}`);
        const finalRule = action.action === "correct" && correctedRule?.trim() ? correctedRule.trim() : action.rule;
        setItems((current) => {
          if (action.action === "reject") {
            return current.filter((item) => {
              const provenance = typeof item.data.provenance === "string" ? item.data.provenance : "";
              const rule = typeof item.data.rule === "string" ? item.data.rule : item.title;
              return !(item.kind === "world_model_candidate" && provenance === action.provenance && rule === action.rule);
            });
          }
          return current.map((item) => {
            const provenance = typeof item.data.provenance === "string" ? item.data.provenance : "";
            const rule = typeof item.data.rule === "string" ? item.data.rule : item.title;
            if (item.kind !== "world_model_candidate" || provenance !== action.provenance || rule !== action.rule) return item;
            const reviewRequired = action.action === "rollback";
            const confidence = action.action === "correct" ? Math.max(Number(item.data.confidence ?? 0), 0.9) : Number(item.data.confidence ?? 0);
            return {
              ...item,
              title: finalRule,
              subtitle: `${reviewRequired ? "review required" : "accepted"} / confidence ${confidence.toFixed(2)} / ${action.provenance}`,
              data: {
                ...item.data,
                rule: finalRule,
                confidence,
                review_required: reviewRequired
              }
            };
          });
        });
        setStatus(`Review ${action.action} stored.`);
      } else if (action.type === "sync-kaggle") {
        setStatus("Syncing Kaggle run outputs.");
        const response = await authedFetch(`/v1/training/kaggle/${encodeURIComponent(action.runId)}/sync`, { method: "POST" });
        if (!response.ok) throw new Error(`sync failed with HTTP ${response.status}`);
        setStatus("Kaggle sync requested.");
      } else if (action.type === "replay-canvas") {
        await scheduleCanvas();
        return;
      } else if (action.type === "replay-invention") {
        setStatus("Replaying invention.");
        const response = await authedFetch("/v1/invention/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: context.userId, goal: action.goal, domain: action.domain })
        });
        if (!response.ok) throw new Error(`replay failed with HTTP ${response.status}`);
        setStatus("Invention replay queued.");
      }
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Record action failed.");
    } finally {
      setActionBusy(null);
    }
  }

  function clearTrainingContent() {
    setContent("");
    if (trainingTextRef.current) {
      trainingTextRef.current.value = "";
    }
  }

  async function ingest(nextContent = content, nextModality = modality) {
    if (!nextContent.trim()) return;
    const context = supabaseUserContext();
    setStatus("Ingesting.");
    try {
      const response = await fetch(`${apiBase}/v1/training/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          user_id: context.userId,
          workspace_id: context.workspaceId,
          content: nextContent,
          modality: nextModality,
          source_trust: sourceTrust,
          domain_hint: domainHint
        })
      });
      if (!response.ok) throw new Error(`ingest failed with HTTP ${response.status}`);
      const data = (await response.json()) as IngestResponse;
      clearTrainingContent();
      setStatus(`signature ${data.signature.id} stored; SPPE ${data.sppe_training_pair.accepted ? "accepted" : "queued"}`);
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Ingest failed.");
    }
  }

  async function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const detected = detectModality(file);
    const value = detected === "text" || detected === "code" || detected === "data" ? await file.text() : await readAsDataUrl(file);
    setContent(value);
    setModality(detected);
    await ingest(value, detected);
    event.target.value = "";
  }

  async function scheduleCanvas() {
    const context = supabaseUserContext();
    setStatus("Queueing canvas.");
    const response = await fetch(`${apiBase}/v1/canvas/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ user_id: context.userId, dataset_ref: context.workspaceId ?? "workspace://training-session", scope: "session_uploads" })
    }).catch((error) => {
      setStatus(error instanceof Error ? `Canvas request failed: ${error.message}` : "Canvas request failed.");
      return null;
    });
    if (response && !response.ok) setStatus(`Canvas request failed with HTTP ${response.status}.`);
    await refresh();
  }

  async function scheduleInvention() {
    const context = supabaseUserContext();
    setStatus("Queueing invention.");
    const response = await fetch(`${apiBase}/v1/invention/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ user_id: context.userId, goal: "Find a robust architecture improvement from current training signals.", domain: domainHint })
    }).catch((error) => {
      setStatus(error instanceof Error ? `Invention request failed: ${error.message}` : "Invention request failed.");
      return null;
    });
    if (response && !response.ok) setStatus(`Invention request failed with HTTP ${response.status}.`);
    await refresh();
  }

  async function scheduleKaggleEncoderRun() {
    const context = supabaseUserContext();
    setStatus("Submitting Kaggle encoder run.");
    try {
      const response = await fetch(`${apiBase}/v1/training/kaggle/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          user_id: context.userId,
          workspace_id: context.workspaceId,
          task_type: "encoder_finetune",
          title: "JIMS-AI encoder fine-tune",
          notes: `domain:${domainHint}`,
          gpu: true
        })
      });
      if (!response.ok) throw new Error("kaggle run failed");
      const data = (await response.json()) as KaggleRunResponse;
      setStatus(`Kaggle ${data.status}: ${data.kernel_ref ?? data.local_path ?? data.run_id}`);
    } catch {
      setStatus("Kaggle submission unavailable.");
    }
    await refresh();
  }

  async function scheduleKaggleRendererRun() {
    const context = supabaseUserContext();
    setStatus("Submitting Kaggle SPPE renderer run.");
    try {
      const response = await fetch(`${apiBase}/v1/training/kaggle/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          user_id: context.userId,
          workspace_id: context.workspaceId,
          task_type: "sppe_renderer_finetune",
          title: "JIMS-AI SPPE renderer fine-tune",
          notes: `domain:${domainHint}`,
          gpu: true
        })
      });
      if (!response.ok) throw new Error("kaggle run failed");
      const data = (await response.json()) as KaggleRunResponse;
      setStatus(`Kaggle ${data.status}: ${data.kernel_ref ?? data.local_path ?? data.run_id}`);
    } catch {
      setStatus("Kaggle renderer submission unavailable.");
    }
    await refresh();
  }

  return (
    <main className="trainingPageShell">
      <aside className="panelNav" aria-label="Training panels">
        {panelDefinitions.map((definition) => (
          <Link className={definition.id === panelId ? "active" : ""} href={`/training/${definition.id}`} key={definition.id}>
            {panelIcons[definition.id]}
            <span>
              <small>{definition.number}</small>
              <strong>{definition.title}</strong>
            </span>
          </Link>
        ))}
      </aside>

      <section className="panelPage">
        <header className="pageTitle">
          <div>
            <p className="eyebrow">{panel.number}</p>
            <h1>{panel.title}</h1>
          </div>
          <div className="buttonRow">
            <span className="resultCount">{total} records</span>
            <button className="iconTextButton" type="button" disabled={loading} onClick={refresh}>
              <RefreshCw size={16} /> {loading ? "Loading" : "Refresh"}
            </button>
          </div>
        </header>

        {panelId === "ingestion" ? (
          <section className="trainingEditor inline">
            <div className="fieldGrid">
              <label>
                Domain hint
                <input value={domainHint} onChange={(event) => setDomainHint(event.target.value)} />
              </label>
              <label>
                Modality
                <select value={modality} onChange={(event) => setModality(event.target.value)}>
                  <option value="text">text</option>
                  <option value="code">code</option>
                  <option value="image">image</option>
                  <option value="audio">audio</option>
                  <option value="video">video</option>
                  <option value="data">data</option>
                </select>
              </label>
              <label>
                Source trust
                <input type="number" min="0" max="1" step="0.01" value={sourceTrust} onChange={(event) => setSourceTrust(Number(event.target.value))} />
              </label>
            </div>

            <textarea ref={trainingTextRef} className="trainingText" value={content} onChange={(event) => setContent(event.target.value)} aria-label="Training content" />
            <div className="buttonRow">
              <input ref={fileInputRef} type="file" hidden onChange={handleFileSelected} />
              <button className="iconTextButton" type="button" onClick={() => fileInputRef.current?.click()}><FileUp size={16} /> Upload</button>
              <button className="sendButton" type="button" disabled={loading} onClick={() => ingest()}><HardDriveUpload size={18} /><span>{loading ? "Ingesting" : "Ingest"}</span></button>
              <button className="iconTextButton" type="button" onClick={scheduleCanvas}><GitBranch size={16} /> Canvas</button>
              <button className="iconTextButton" type="button" onClick={scheduleInvention}><Route size={16} /> Invention</button>
            </div>
          </section>
        ) : null}

        {panelId === "pipeline" ? (
          <section className="trainingEditor inline">
            <div className="buttonRow">
              <button className="iconTextButton" type="button" onClick={scheduleKaggleEncoderRun}>
                <Cpu size={16} /> Kaggle Encoder
              </button>
              <button className="iconTextButton" type="button" onClick={scheduleKaggleRendererRun}>
                <Cpu size={16} /> Kaggle Renderer
              </button>
            </div>
          </section>
        ) : null}

        <p className="statusLine">{status}</p>

        <section className="storedDataList">
          {loading && !items.length ? <div className="panelLoading"><RefreshCw size={18} /> {loadingLabel || "Loading records."}</div> : null}
          {items.length ? items.map((item, index) => (
            <StoredDataItem
              actionBusy={actionBusy}
              item={item}
              key={`${panelId}-${item.id}-${index}`}
              onAction={handleRecordAction}
              panelId={panelId}
            />
          )) : !loading ? <div className="emptyState">No records.</div> : null}
          <div ref={sentinelRef} className="scrollSentinel">
            {loading && items.length ? <><RefreshCw size={15} /> {loadingLabel || "Loading more records."}</> : hasMore ? "" : "End"}
          </div>
        </section>
      </section>
    </main>
  );
}

function StoredDataItem({
  actionBusy,
  item,
  onAction,
  panelId
}: {
  actionBusy: string | null;
  item: TrainingPanelItem;
  onAction: (action: RecordAction) => void;
  panelId: string;
}) {
  const metrics = item.kind === "pipeline_monitor" || item.kind === "provider_readiness" ? item.data : null;
  const signature = item.kind === "signature" ? item.data : null;
  const ingest = item.kind === "training_ingest" ? item.data : null;
  const kaggle = item.kind === "kaggle_training_run" ? item.data : null;
  const candidate = item.kind === "world_model_candidate" ? item.data : null;
  const session = item.kind === "canvas_session" || item.kind === "invention_session" ? item.data : null;
  return (
    <article className="dataRecord">
      <header>
        <div>
          <span className="recordKind">{item.kind}</span>
          <h2>{item.title}</h2>
          <p>{item.subtitle}</p>
        </div>
        <time>{new Date(item.created_at).toLocaleString()}</time>
      </header>
      <RecordActions actionBusy={actionBusy} data={item.data} item={item} onAction={onAction} panelId={panelId} />
      {item.kind === "pipeline_monitor" ? <SystemHealthBlock data={item.data} /> : null}
      {metrics ? <MetricBlock data={metrics} /> : null}
      {signature ? <SignatureBlock data={signature} /> : null}
      {ingest ? <IngestBlock data={ingest} /> : null}
      {candidate ? <WorldModelBlock data={candidate} /> : null}
      {session ? <SessionBlock data={session} kind={item.kind} /> : null}
      {kaggle ? <KaggleRunBlock data={kaggle} /> : null}
      {!metrics && !signature && !ingest && !candidate && !session && !kaggle ? <pre className="jsonBlock">{JSON.stringify(item.data, null, 2)}</pre> : null}
    </article>
  );
}

function RecordActions({
  actionBusy,
  data,
  item,
  onAction,
  panelId
}: {
  actionBusy: string | null;
  data: Record<string, unknown>;
  item: TrainingPanelItem;
  onAction: (action: RecordAction) => void;
  panelId: string;
}) {
  const signatureData = item.kind === "training_ingest" ? data.signature as Record<string, unknown> | undefined : item.kind === "signature" ? data : undefined;
  const signatureId = typeof signatureData?.id === "string" ? signatureData.id : "";
  const rawExcerpt = String(signatureData?.raw_excerpt ?? "");
  const provenance = typeof data.provenance === "string" ? data.provenance : "";
  const rule = typeof data.rule === "string" ? data.rule : item.title;
  const runId = typeof data.run_id === "string" ? data.run_id : "";
  const goal = typeof data.goal === "string" ? data.goal : item.title;
  const domain = typeof data.domain === "string" ? data.domain : "systems";
  const busy = Boolean(actionBusy);

  if (panelId === "memory" && signatureId) {
    return (
      <div className="recordActions">
        <button className="iconTextButton compact" type="button" disabled={busy} onClick={() => onAction({ type: "update-memory", signatureId, currentContent: rawExcerpt })}><Pencil size={15} /> Update</button>
        <button className="iconTextButton compact danger" type="button" disabled={busy} onClick={() => onAction({ type: "delete-memory", signatureId })}><Trash2 size={15} /> Delete</button>
      </div>
    );
  }
  if (panelId === "ingestion" && signatureId) {
    return (
      <div className="recordActions">
        <button className="iconTextButton compact" type="button" disabled={busy} onClick={() => onAction({ type: "update-memory", signatureId, currentContent: rawExcerpt })}><Pencil size={15} /> Update</button>
        <button className="iconTextButton compact danger" type="button" disabled={busy} onClick={() => onAction({ type: "delete-memory", signatureId })}><Trash2 size={15} /> Delete</button>
      </div>
    );
  }
  if ((panelId === "review" || panelId === "world-model") && item.kind === "world_model_candidate" && provenance && rule) {
    return (
      <div className="recordActions">
        <button className="iconTextButton compact" type="button" disabled={busy} onClick={() => onAction({ type: "review", action: "accept", provenance, rule })}><Check size={15} /> Accept</button>
        <button className="iconTextButton compact" type="button" disabled={busy} onClick={() => onAction({ type: "review", action: "correct", provenance, rule })}><Pencil size={15} /> Correct</button>
        <button className="iconTextButton compact" type="button" disabled={busy} onClick={() => onAction({ type: "review", action: "promote", provenance, rule })}><ClipboardCheck size={15} /> Promote</button>
        <button className="iconTextButton compact danger" type="button" disabled={busy} onClick={() => onAction({ type: "review", action: "reject", provenance, rule })}><X size={15} /> Reject</button>
        <button className="iconTextButton compact" type="button" disabled={busy} onClick={() => onAction({ type: "review", action: "rollback", provenance, rule })}><RotateCcw size={15} /> Rollback</button>
      </div>
    );
  }
  if (panelId === "sessions" && item.kind === "kaggle_training_run" && runId) {
    return (
      <div className="recordActions">
        <button className="iconTextButton compact" type="button" disabled={busy} onClick={() => onAction({ type: "sync-kaggle", runId })}><RefreshCw size={15} /> Sync</button>
      </div>
    );
  }
  if (panelId === "sessions" && item.kind === "canvas_session") {
    return (
      <div className="recordActions">
        <button className="iconTextButton compact" type="button" disabled={busy} onClick={() => onAction({ type: "replay-canvas" })}><RotateCcw size={15} /> Replay</button>
      </div>
    );
  }
  if (panelId === "sessions" && item.kind === "invention_session") {
    return (
      <div className="recordActions">
        <button className="iconTextButton compact" type="button" disabled={busy} onClick={() => onAction({ type: "replay-invention", goal, domain })}><RotateCcw size={15} /> Replay</button>
      </div>
    );
  }
  return null;
}

function KaggleRunBlock({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="recordBody">
      <div className="recordStats">
        <span>{String(data.status ?? "unknown")}</span>
        <span>{String(data.task_type ?? "training")}</span>
      </div>
      <p>{String(data.detail ?? "")}</p>
      <pre className="jsonBlock">{JSON.stringify({ kernel_ref: data.kernel_ref, local_path: data.local_path }, null, 2)}</pre>
    </div>
  );
}

function WorldModelBlock({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="recordBody">
      <p>{String(data.rule ?? "")}</p>
      <div className="recordStats">
        <span>{String(data.review_required ?? false) === "true" ? "review required" : "accepted"}</span>
        <span>confidence {Number(data.confidence ?? 0).toFixed(2)}</span>
        <span>{String(data.provenance ?? "unknown source")}</span>
      </div>
    </div>
  );
}

function SessionBlock({ data, kind }: { data: Record<string, unknown>; kind: string }) {
  return (
    <div className="recordBody">
      <div className="recordStats">
        <span>{String(data.status ?? "unknown")}</span>
        <span>{kind.replace("_", " ")}</span>
      </div>
      <p>{String(data.goal ?? data.dataset_ref ?? "")}</p>
    </div>
  );
}

function MetricBlock({ data }: { data: Record<string, unknown> }) {
  const hiddenKeys = new Set(["auto_training", "system_health_next_step"]);
  const entries = Object.entries(data).filter(([key]) => !hiddenKeys.has(key));
  return (
    <div className="metricGrid wide">
      {entries.map(([key, value]) => (
        <div className="metric" key={key}>
          <strong>{typeof value === "object" && value !== null ? JSON.stringify(value) : String(value)}</strong>
          <span>{key}</span>
        </div>
      ))}
    </div>
  );
}

function SystemHealthBlock({ data }: { data: Record<string, unknown> }) {
  if (typeof data.system_health_score === "undefined") return null;
  return (
    <div className="systemHealthBlock">
      <div>
        <span className="recordKind">System health</span>
        <strong>{String(data.system_health_score)}/100</strong>
      </div>
      <p>
        Limited by {String(data.system_health_limiting_factor ?? "unknown")}. {String(data.system_health_next_step ?? "")}
      </p>
    </div>
  );
}

function SignatureBlock({ data }: { data: Record<string, unknown> }) {
  const structured = data.structured as { entities?: Array<{ name: string }>; relations?: unknown[]; causal_chain?: unknown[] } | undefined;
  return (
    <div className="recordBody">
      <p>{String(data.raw_excerpt ?? "")}</p>
      <div className="pillGroup">
        {structured?.entities?.map((entity) => <span className="pill" key={entity.name}>{entity.name}</span>)}
      </div>
      <div className="recordStats">
        <span>{structured?.relations?.length ?? 0} relations</span>
        <span>{structured?.causal_chain?.length ?? 0} causal links</span>
      </div>
    </div>
  );
}

function IngestBlock({ data }: { data: Record<string, unknown> }) {
  const signature = data.signature as Record<string, unknown> | undefined;
  const candidates = data.world_model_candidates as unknown[] | undefined;
  const trainingDecision = data.auto_training_decision as Record<string, unknown> | undefined;
  return (
    <div className="recordBody">
      <p>{String(signature?.raw_excerpt ?? "")}</p>
      <div className="recordStats">
        <span>{candidates?.length ?? 0} world-model candidates</span>
        <span>{String((data.sppe_training_pair as Record<string, unknown> | undefined)?.accepted ?? false)}</span>
        {trainingDecision ? <span>{String(trainingDecision.task_type ?? "training")} {trainingDecision.should_schedule ? "ready" : "watching"}</span> : null}
      </div>
      {trainingDecision ? <p>{String(trainingDecision.reason ?? "")}</p> : null}
    </div>
  );
}

function detectModality(file: File) {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("audio/")) return "audio";
  if (file.type.startsWith("video/")) return "video";
  if (/\.(ts|tsx|js|jsx|py|go|rs|java|cs|cpp|c|h|sql|yaml|yml|json)$/i.test(file.name)) return "code";
  if (file.type.includes("json") || file.name.endsWith(".csv")) return "data";
  return "text";
}

function readAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
