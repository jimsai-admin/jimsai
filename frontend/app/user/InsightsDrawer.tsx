// frontend/app/user/InsightsDrawer.tsx
"use client";

import { useState } from "react";
import { X, ChevronRight, Copy, Check, Database, BookOpen, Trash2 } from "lucide-react";
import { useChatStore } from "./store";
import type { Message } from "./types";

const TABS = [
  "Answer State",
  "Sources",
  "Reasoning",
  "Simulation",
  "Capability",
  "Gaps",
  "Memory Controls",
] as const;
type Tab = (typeof TABS)[number];

type Props = {
  apiBase: string;
  authHeaders: () => Record<string, string>;
  userId: string;
  workspaceId: string | undefined;
};

export default function InsightsDrawer({ apiBase, authHeaders, userId, workspaceId }: Props) {
  const store = useChatStore();
  const {
    drawerOpen,
    drawerMessageIndex,
    drawerTab,
    messages,
    activeThreadId,
    learnedSignatureIds,
    feedbackStatus,
  } = store;

  const threadMessages = messages[activeThreadId] ?? [];
  const message: Message | null =
    drawerMessageIndex !== null ? (threadMessages[drawerMessageIndex] ?? null) : null;
  const api = message?.apiResponse ?? null;

  const [sourceLearnStatus, setSourceLearnStatus] = useState<Record<string, string>>({});
  const [expandedSource, setExpandedSource] = useState<string | null>(null);
  const [copiedSource, setCopiedSource] = useState<string | null>(null);

  if (!drawerOpen) return null;

  const copySource = (s: string) => {
    navigator.clipboard.writeText(s).then(() => {
      setCopiedSource(s);
      setTimeout(() => setCopiedSource((c) => (c === s ? null : c)), 1400);
    }, () => {});
  };

  const handleLearnSource = async (sourceId: string) => {
    setSourceLearnStatus((s) => ({ ...s, [sourceId]: "learning…" }));
    try {
      const res = await fetch(`${apiBase}/v1/training/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          user_id: userId,
          workspace_id: workspaceId,
          content: sourceId,
          modality: "text",
          source_trust: 0.85,
          domain_hint: "user_confirm_source",
        }),
      });
      if (!res.ok) throw new Error("failed");
      const d = (await res.json()) as { signature?: { id?: string } };
      setSourceLearnStatus((s) => ({ ...s, [sourceId]: d.signature?.id ?? "learned" }));
    } catch {
      setSourceLearnStatus((s) => ({ ...s, [sourceId]: "error" }));
    }
  };

  const handleUnlearnSource = async (sourceId: string) => {
    const sigId = sourceLearnStatus[sourceId];
    if (!sigId || sigId === "learning…" || sigId === "error" || sigId === "learned") return;
    await fetch(`${apiBase}/v1/memory/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        user_id: userId,
        workspace_id: workspaceId,
        signature_id: sigId,
        reason: "user_unlearn_source",
      }),
    });
    setSourceLearnStatus((s) => {
      const n = { ...s };
      delete n[sourceId];
      return n;
    });
  };

  const renderTab = (tab: Tab) => {
    if (!api) return <div className="muted">No data for this message.</div>;

    switch (tab) {
      case "Answer State":
        return (
          <div className="metricGrid compact">
            <div className="metric">
              <strong>{api.confidence.toFixed(2)}</strong>
              <span>confidence</span>
            </div>
            <div className="metric">
              <strong>{api.sources.length}</strong>
              <span>sources</span>
            </div>
            <div className="metric">
              <strong>{api.gaps.length}</strong>
              <span>gaps</span>
            </div>
            <div className="metric">
              <strong>{api.capability_plan?.kind ?? "n/a"}</strong>
              <span>capability</span>
            </div>
          </div>
        );

      case "Sources":
        return api.sources.length ? (
          <div className="sourceList">
            {api.sources.map((s, i) => {
              const status = sourceLearnStatus[s];
              const learned = status && status !== "learning…" && status !== "error";
              const open = expandedSource === s;
              // Where in the reasoning was this source used? (feels alive)
              const usedIn = api.trace.find((t) => JSON.stringify(t.data ?? {}).includes(s));
              return (
                <div key={s} className={`sourceCard${open ? " open" : ""}`}>
                  <button
                    className="sourceHead"
                    type="button"
                    onClick={() => setExpandedSource(open ? null : s)}
                    aria-expanded={open}
                  >
                    <Database size={14} className="sourceIcon" />
                    <span className="sourceLabel">{`Source ${i + 1}`}</span>
                    <span className="sourceRef">{s.slice(0, 14)}…</span>
                    <ChevronRight size={15} className="sourceChevron" />
                  </button>
                  {open && (
                    <div className="sourceBody">
                      <div className="sourceIdRow">
                        <code>{s}</code>
                        <button
                          className="iconButton compact"
                          type="button"
                          title="Copy id"
                          onClick={() => copySource(s)}
                        >
                          {copiedSource === s ? <Check size={13} /> : <Copy size={13} />}
                        </button>
                      </div>
                      {usedIn && (
                        <p className="sourceUsage">
                          <span className="sourceUsageStage">{usedIn.stage}</span> {usedIn.message}
                        </p>
                      )}
                      <div className="sourceActions">
                        {!learned ? (
                          <button
                            className="iconTextButton compact"
                            type="button"
                            onClick={() => handleLearnSource(s)}
                            disabled={status === "learning…"}
                          >
                            <BookOpen size={13} /> {status === "learning…" ? "Learning…" : "Keep in memory"}
                          </button>
                        ) : (
                          <button
                            className="iconTextButton compact danger"
                            type="button"
                            onClick={() => handleUnlearnSource(s)}
                          >
                            <Trash2 size={13} /> Unlearn
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="muted">This answer used no stored sources.</div>
        );

      case "Reasoning":
        return (
          <div className="traceList">
            {api.layer_results.length ? (
              api.layer_results.map((lr) => (
                <div className="layerRow" key={lr.layer}>
                  <span className={`state ${lr.activated ? "on" : ""}`} />
                  <div>
                    <strong>{lr.layer}</strong>
                    <small>{lr.deterministic ? "deterministic" : "bounded model"}</small>
                    <small>{lr.summary}</small>
                  </div>
                </div>
              ))
            ) : (
              <div className="muted">No layer results.</div>
            )}
          </div>
        );

      case "Simulation":
        return api.simulation_results.length ? (
          <div className="traceList">
            {api.simulation_results.map((sim) => (
              <div className="traceItem" key={sim.scenario}>
                <strong>{sim.scenario}</strong>
                <span>
                  {sim.passed ? "✓ passed" : "✗ failed"} — {sim.confidence.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted">No simulation results.</div>
        );

      case "Capability":
        return api.capability_plan ? (
          <div className="traceList">
            <div className="traceItem">
              <strong>{api.capability_plan.kind}</strong>
              <span>
                {api.capability_plan.route} / {api.capability_plan.context_strategy} / energy{" "}
                {api.capability_plan.energy_profile}
              </span>
              <span>{api.capability_plan.reason}</span>
            </div>
            {(api.capability_results ?? []).map((r) => (
              <div className="traceItem" key={`${r.adapter}-${r.status}`}>
                <strong>{r.status}</strong>
                <span>{r.adapter}</span>
                <span>{r.summary}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted">No capability plan.</div>
        );

      case "Gaps":
        return api.gaps.length ? (
          <div className="traceList">
            {api.gaps.map((g, i) => (
              <div
                className="traceItem"
                key={i}
                style={{ borderLeftColor: "var(--warn)", background: "var(--warn-soft)" }}
              >
                {g}
              </div>
            ))}
          </div>
        ) : (
          <div className="muted" style={{ color: "var(--good)" }}>
            No gaps detected.
          </div>
        );

      case "Memory Controls": {
        const traceId = api.ir.trace_id;
        const learnedSigId = learnedSignatureIds[traceId];
        return (
          <div style={{ display: "grid", gap: 12 }}>
            <div className="muted" style={{ fontSize: 11, fontFamily: "monospace" }}>
              trace_id: {traceId}
            </div>
            {!learnedSigId ? (
              <button
                className="sendButton"
                type="button"
                style={{ width: "fit-content" }}
                onClick={() =>
                  message && store.learnResponse(message, apiBase, authHeaders(), userId, workspaceId)
                }
              >
                Learn this response
              </button>
            ) : (
              <button
                className="iconTextButton danger"
                type="button"
                onClick={() =>
                  store.unlearnResponse(traceId, apiBase, authHeaders(), userId, workspaceId)
                }
              >
                Unlearn
              </button>
            )}
            {feedbackStatus && (
              <div className="muted" style={{ fontSize: 12 }}>
                {feedbackStatus}
              </div>
            )}
          </div>
        );
      }

      default:
        return null;
    }
  };

  return (
    <>
      <div className="drawerBackdrop" onClick={() => store.closeDrawer()} />
      <div className="insightsDrawer" role="dialog" aria-label="Response insights">
        <div className="drawerHandle" />
        <div className="drawerHeader">
          <strong>Response Insights</strong>
          <button className="iconButton compact" type="button" onClick={() => store.closeDrawer()}>
            <X size={16} />
          </button>
        </div>
        <div className="drawerTabs">
          {TABS.map((t) => (
            <button
              key={t}
              className={`drawerTab${drawerTab === t ? " active" : ""}`}
              type="button"
              onClick={() => store.setDrawerTab(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="drawerBody">{renderTab(drawerTab as Tab)}</div>
      </div>
    </>
  );
}
