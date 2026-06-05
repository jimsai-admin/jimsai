// frontend/app/user/Sidebar.tsx
"use client";

import { useState } from "react";
import { Plus, MessageSquare, BookOpen, X, Search, Trash2, Pencil } from "lucide-react";
import { useChatStore } from "./store";

function createThreadId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `thread_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 2) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

type Props = {
  userInitials: string;
  apiBase: string;
  authHeaders: () => Record<string, string>;
  userId: string;
  workspaceId: string | undefined;
  onSignOut: () => void;
};

export default function Sidebar({
  userInitials,
  apiBase,
  authHeaders,
  userId,
  workspaceId,
  onSignOut,
}: Props) {
  const store = useChatStore();
  const { sidebarPanel, threads, activeThreadId } = store;
  const [search, setSearch] = useState("");
  const [learnContent, setLearnContent] = useState("");
  const [learnStatus, setLearnStatus] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const filteredThreads = threads.filter((t) =>
    t.title.toLowerCase().includes(search.toLowerCase())
  );

  const handleNewThread = () => {
    const id = createThreadId();
    store.upsertThread({ id, title: "New chat", updated_at: new Date().toISOString() });
    store.setActiveThreadId(id);
    store.setSidebarPanel(null);
  };

  const handleLearn = async () => {
    if (!learnContent.trim()) return;
    setLearnStatus("Teaching…");
    try {
      const res = await fetch(`${apiBase}/v1/training/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          user_id: userId,
          workspace_id: workspaceId,
          content: learnContent.trim(),
          modality: "text",
          source_trust: 0.8,
          domain_hint: "user_teach_workspace",
        }),
      });
      setLearnStatus(res.ok ? "✓ Learned into workspace" : "✗ Failed to learn");
      if (res.ok) setLearnContent("");
    } catch {
      setLearnStatus("✗ Network error");
    }
  };

  const startRename = (id: string, title: string) => {
    setRenamingId(id);
    setRenameValue(title);
  };

  const commitRename = () => {
    if (renamingId && renameValue.trim()) store.renameThread(renamingId, renameValue.trim());
    setRenamingId(null);
  };

  return (
    <div style={{ position: "relative", display: "flex", flexShrink: 0 }}>
      {/* ── Icon sidebar ──────────────────────────────────────────────── */}
      <div className="sidebar">
        <div className="brandMark" style={{ marginBottom: 6 }}>
          J
        </div>
        <button className="iconButton compact" title="New chat" type="button" onClick={handleNewThread}>
          <Plus size={16} />
        </button>
        <button
          className={`iconButton compact${sidebarPanel === "threads" ? " active" : ""}`}
          title="Thread history"
          type="button"
          onClick={() => store.setSidebarPanel(sidebarPanel === "threads" ? null : "threads")}
        >
          <MessageSquare size={16} />
        </button>
        <button
          className={`iconButton compact${sidebarPanel === "learn" ? " active" : ""}`}
          title="Teach workspace"
          type="button"
          onClick={() => store.setSidebarPanel(sidebarPanel === "learn" ? null : "learn")}
        >
          <BookOpen size={16} />
        </button>
        <div className="sidebarBottom">
          <button className="avatarCircle" title="Sign out" type="button" onClick={onSignOut}>
            {userInitials}
          </button>
        </div>
      </div>

      {/* ── Thread history panel ───────────────────────────────────────── */}
      {sidebarPanel === "threads" && (
        <div className="sidePanel">
          <div className="sidePanelHeader">
            <h2>Chats</h2>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                className="iconButton compact"
                type="button"
                title="New chat"
                onClick={handleNewThread}
              >
                <Plus size={14} />
              </button>
              <button
                className="iconButton compact"
                type="button"
                onClick={() => store.setSidebarPanel(null)}
              >
                <X size={14} />
              </button>
            </div>
          </div>
          <div className="sidePanelSearch">
            <div style={{ position: "relative" }}>
              <Search
                size={13}
                style={{
                  position: "absolute",
                  left: 8,
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "var(--muted)",
                  pointerEvents: "none",
                }}
              />
              <input
                placeholder="Search chats…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                  paddingLeft: 28,
                  width: "100%",
                  height: 36,
                  borderRadius: "var(--radius)",
                  border: "1px solid var(--line)",
                  background: "var(--surface)",
                  color: "var(--ink)",
                  fontSize: 13,
                }}
              />
            </div>
          </div>
          <div style={{ overflowY: "auto", flex: 1 }}>
            {filteredThreads.map((t) => (
              <div
                key={t.id}
                className={`threadItem${t.id === activeThreadId ? " active" : ""}`}
                onClick={() => {
                  store.setActiveThreadId(t.id);
                  store.setSidebarPanel(null);
                }}
              >
                {renamingId === t.id ? (
                  <input
                    value={renameValue}
                    autoFocus
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={commitRename}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitRename();
                      if (e.key === "Escape") setRenamingId(null);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    style={{
                      flex: 1,
                      fontSize: 13,
                      border: "1px solid var(--accent)",
                      borderRadius: 4,
                      padding: "2px 6px",
                      background: "var(--surface)",
                      color: "var(--ink)",
                    }}
                  />
                ) : (
                  <span
                    style={{
                      flex: 1,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {t.title}
                  </span>
                )}
                <span className="threadTimestamp">{relativeTime(t.updated_at)}</span>
                <button
                  className="iconButton compact"
                  type="button"
                  title="Rename thread"
                  onClick={(e) => {
                    e.stopPropagation();
                    startRename(t.id, t.title);
                  }}
                  style={{ width: 22, height: 22, minWidth: 22, minHeight: 22, opacity: 0.6 }}
                >
                  <Pencil size={11} />
                </button>
                <button
                  className="iconButton compact"
                  type="button"
                  title="Delete thread"
                  onClick={(e) => {
                    e.stopPropagation();
                    store.deleteThread(t.id, apiBase, authHeaders(), userId);
                  }}
                  style={{
                    width: 22,
                    height: 22,
                    minWidth: 22,
                    minHeight: 22,
                    color: "var(--danger)",
                    opacity: 0.7,
                  }}
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
            {!filteredThreads.length && (
              <div className="muted" style={{ padding: "14px" }}>
                No threads found.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Learn panel ────────────────────────────────────────────────── */}
      {sidebarPanel === "learn" && (
        <div className="sidePanel">
          <div className="sidePanelHeader">
            <h2>Teach Workspace</h2>
            <button
              className="iconButton compact"
              type="button"
              onClick={() => store.setSidebarPanel(null)}
            >
              <X size={14} />
            </button>
          </div>
          <div
            style={{ padding: "12px 14px", display: "grid", gap: 10, flex: 1, overflowY: "auto" }}
          >
            <p className="muted" style={{ margin: 0, fontSize: 12 }}>
              Paste content, facts, or documents to teach JimsAI your workspace knowledge.
            </p>
            <textarea
              value={learnContent}
              onChange={(e) => setLearnContent(e.target.value)}
              rows={8}
              placeholder="Paste text, facts, or documents here…"
              style={{
                width: "100%",
                resize: "vertical",
                padding: 10,
                borderRadius: "var(--radius)",
                border: "1px solid var(--line)",
                background: "var(--surface)",
                color: "var(--ink)",
                fontSize: 13,
                lineHeight: 1.45,
              }}
            />
            <button
              className="sendButton"
              type="button"
              onClick={handleLearn}
              disabled={!learnContent.trim()}
            >
              Teach workspace
            </button>
            {learnStatus && (
              <div className="muted" style={{ fontSize: 12 }}>
                {learnStatus}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
