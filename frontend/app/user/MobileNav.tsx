// frontend/app/user/MobileNav.tsx
"use client";

import { useState } from "react";
import { Menu, X, Plus, MessageSquare, BookOpen, ChevronLeft } from "lucide-react";
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
  activeThreadTitle: string;
  userInitials: string;
  userEmail: string;
  apiBase: string;
  authHeaders: () => Record<string, string>;
  userId: string;
  workspaceId: string | undefined;
  onSignOut: () => void;
};

type DrawerView = "menu" | "threads" | "learn";

export default function MobileNav({
  activeThreadTitle,
  userInitials,
  userEmail,
  apiBase,
  authHeaders,
  userId,
  workspaceId,
  onSignOut,
}: Props) {
  const store = useChatStore();
  const { threads, activeThreadId, mobileNavOpen } = store;
  const [view, setView] = useState<DrawerView>("menu");
  const [search, setSearch] = useState("");
  const [learnContent, setLearnContent] = useState("");
  const [learnStatus, setLearnStatus] = useState("");

  const open = () => { store.setMobileNavOpen(true); setView("menu"); };
  const close = () => { store.setMobileNavOpen(false); setView("menu"); };

  const handleNewThread = () => {
    const id = createThreadId();
    store.upsertThread({ id, title: "New chat", updated_at: new Date().toISOString() });
    store.setActiveThreadId(id);
    close();
  };

  const handleSelectThread = (id: string) => {
    store.setActiveThreadId(id);
    close();
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
      setLearnStatus(res.ok ? "✓ Learned" : "✗ Failed");
      if (res.ok) setLearnContent("");
    } catch {
      setLearnStatus("✗ Network error");
    }
  };

  const filteredThreads = threads.filter((t) =>
    t.title.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      {/* Top bar */}
      <div className="mobileTopBar">
        <div className="brandMark" style={{ width: 28, height: 28, fontSize: 14 }}>J</div>
        <span className="mobileTopBarTitle">{activeThreadTitle || "JimsAI"}</span>
        <button className="iconButton compact" type="button" onClick={open} aria-label="Open navigation">
          <Menu size={20} />
        </button>
      </div>

      {/* Backdrop */}
      {mobileNavOpen && (
        <div className="mobileNavBackdrop" onClick={close} />
      )}

      {/* Drawer */}
      {mobileNavOpen && (
        <div className="mobileNavDrawer">
          {/* Header */}
          <div className="mobileNavHeader">
            {view !== "menu" ? (
              <button className="iconButton compact" type="button" onClick={() => setView("menu")}>
                <ChevronLeft size={16} />
              </button>
            ) : (
              <div className="brandMark" style={{ width: 28, height: 28, fontSize: 14 }}>J</div>
            )}
            <span style={{ fontWeight: 700, fontSize: 15 }}>
              {view === "menu" ? "JimsAI" : view === "threads" ? "Chats" : "Teach Workspace"}
            </span>
            <button className="iconButton compact" type="button" onClick={close}>
              <X size={16} />
            </button>
          </div>

          {/* Menu view */}
          {view === "menu" && (
            <div className="mobileNavItems">
              <button className="mobileNavItem" type="button" onClick={handleNewThread}>
                <Plus size={18} /> <span>New Chat</span>
              </button>
              <button className="mobileNavItem" type="button" onClick={() => setView("threads")}>
                <MessageSquare size={18} /> <span>Thread History</span>
              </button>
              <button className="mobileNavItem" type="button" onClick={() => setView("learn")}>
                <BookOpen size={18} /> <span>Teach Workspace</span>
              </button>
            </div>
          )}

          {/* Threads view */}
          {view === "threads" && (
            <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
              <div style={{ padding: "8px 14px" }}>
                <input
                  placeholder="Search chats…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{
                    width: "100%",
                    height: 36,
                    padding: "0 12px",
                    borderRadius: "var(--radius)",
                    border: "1px solid var(--line)",
                    background: "var(--surface)",
                    color: "var(--ink)",
                    fontSize: 13,
                  }}
                />
              </div>
              <div style={{ overflowY: "auto", flex: 1 }}>
                {filteredThreads.map((t) => (
                  <button
                    key={t.id}
                    className={`mobileNavItem${t.id === activeThreadId ? " active" : ""}`}
                    type="button"
                    onClick={() => handleSelectThread(t.id)}
                    style={{ justifyContent: "space-between" }}
                  >
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {t.title}
                    </span>
                    <span style={{ color: "var(--muted)", fontSize: 11, flexShrink: 0 }}>
                      {relativeTime(t.updated_at)}
                    </span>
                  </button>
                ))}
                {!filteredThreads.length && (
                  <div className="muted" style={{ padding: 14, fontSize: 13 }}>No threads.</div>
                )}
              </div>
            </div>
          )}

          {/* Learn view */}
          {view === "learn" && (
            <div style={{ padding: "12px 14px", display: "grid", gap: 10, flex: 1, overflowY: "auto" }}>
              <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                Paste content to teach JimsAI your workspace knowledge.
              </p>
              <textarea
                value={learnContent}
                onChange={(e) => setLearnContent(e.target.value)}
                rows={7}
                placeholder="Paste text, facts, or documents…"
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
              {learnStatus && <div className="muted" style={{ fontSize: 12 }}>{learnStatus}</div>}
            </div>
          )}

          {/* Profile / sign out — always at bottom */}
          <div className="mobileNavProfile">
            <div className="avatarCircle" style={{ cursor: "default" }}>{userInitials}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {userEmail || "Your account"}
              </div>
            </div>
            <button className="iconTextButton compact danger" type="button" onClick={() => { onSignOut(); close(); }}>
              Sign out
            </button>
          </div>
        </div>
      )}
    </>
  );
}
