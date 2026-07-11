// frontend/app/user/ChatLayout.tsx
"use client";

import { useEffect, useMemo, useCallback, useState } from "react";
import Sidebar from "./Sidebar";
import MobileNav from "./MobileNav";
import MessageList from "./MessageList";
import Composer from "./Composer";
import InsightsDrawer from "./InsightsDrawer";
import { useChatStore } from "./store";
import {
  AUTH_STATE_EVENT,
  clearSupabaseSession,
  refreshSupabaseSession,
  storeSupabaseSession,
  supabaseAuthHeaders,
  supabaseUserContext,
} from "../authHeaders";

// Production default = the deployed Lambda; NEXT_PUBLIC_API_BASE_URL overrides it.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws";

export default function ChatLayout() {
  const store = useChatStore();
  const { activeThreadId, threads, threadsLoaded } = store;

  const [authContext, setAuthContext] = useState(() => supabaseUserContext());
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authStatus, setAuthStatus] = useState(
    supabaseUserContext().authenticated ? "Signed in." : "Sign in to start."
  );
  const [authConfigured, setAuthConfigured] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [backendStatus, setBackendStatus] = useState("Checking runtime…");

  const authHeaders = useCallback(() => supabaseAuthHeaders(), []);

  const userId = authContext.userId;
  const workspaceId = authContext.workspaceId ?? undefined;
  const userEmail = authContext.userId ?? "";
  const userInitials = userEmail
    ? userEmail.slice(0, 2).toUpperCase()
    : "J";

  const activeThreadTitle = useMemo(
    () => threads.find((t) => t.id === activeThreadId)?.title ?? "New chat",
    [threads, activeThreadId]
  );

  // Sync auth state changes
  useEffect(() => {
    function update() {
      setAuthContext(supabaseUserContext());
    }
    window.addEventListener(AUTH_STATE_EVENT, update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener(AUTH_STATE_EVENT, update);
      window.removeEventListener("storage", update);
    };
  }, []);

  // Check backend health
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then(async (r) => {
        const d = (await r.json()) as { status?: string };
        setBackendStatus(d.status === "ok" ? "Runtime ready" : "Runtime reachable");
      })
      .catch(() => setBackendStatus("Runtime unavailable"));
  }, []);

  // Check auth configuration
  useEffect(() => {
    fetch(`${API_BASE}/v1/auth/config`)
      .then(async (r) => {
        const d = (await r.json()) as { configured?: boolean };
        setAuthConfigured(Boolean(d.configured));
      })
      .catch(() => setAuthConfigured(false));
  }, []);

  // Load threads from backend when authenticated
  useEffect(() => {
    if (authContext.authenticated && !threadsLoaded) {
      void store.loadThreads(API_BASE, authHeaders(), userId, workspaceId);
    }
  }, [authContext.authenticated, threadsLoaded, store, authHeaders, userId, workspaceId]);

  // Load messages for active thread when it changes
  useEffect(() => {
    if (authContext.authenticated && activeThreadId) {
      void store.loadMessages(activeThreadId, API_BASE, authHeaders(), userId);
    }
  }, [authContext.authenticated, activeThreadId, store, authHeaders, userId]);

  const signOut = useCallback(() => {
    clearSupabaseSession();
    setAuthContext(supabaseUserContext());
    setAuthStatus("Signed out.");
  }, []);

  async function authenticate(mode: "signin" | "signup") {
    if (!authConfigured || !email.trim() || !password) return;
    setAuthBusy(true);
    setAuthStatus(mode === "signin" ? "Signing in…" : "Creating account…");
    try {
      const res = await fetch(`${API_BASE}/v1/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const data = (await res.json()) as Record<string, unknown>;
      if (!res.ok)
        throw new Error(
          String(data.detail ?? data.msg ?? data.error_description ?? data.error ?? "auth failed")
        );
      storeSupabaseSession(data);
      const ctx = supabaseUserContext();
      setAuthContext(ctx);
      setAuthStatus(ctx.authenticated ? "Signed in." : "Confirm email, then sign in.");
    } catch (err) {
      setAuthStatus(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setAuthBusy(false);
    }
  }

  // ── Auth screen ────────────────────────────────────────────────────────
  if (!authContext.authenticated) {
    return (
      <main className="authShell">
        <section className="authCard">
          <div>
            <p className="eyebrow">Workspace Access</p>
            <h1>Sign in to JimsAI</h1>
            <p>Persistent memory, feedback, and training require a workspace identity.</p>
          </div>
          <div className="authForm">
            <label>
              Email
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
                autoComplete="email"
              />
            </label>
            <label>
              Password
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                autoComplete="current-password"
              />
            </label>
            <div className="buttonRow">
              <button
                className="sendButton"
                type="button"
                disabled={authBusy || !authConfigured}
                onClick={() => authenticate("signin")}
              >
                Sign in
              </button>
              <button
                className="iconTextButton"
                type="button"
                disabled={authBusy || !authConfigured}
                onClick={() => authenticate("signup")}
              >
                Create account
              </button>
            </div>
            <div className="authMeta">
              <span>{authStatus}</span>
              <span>{backendStatus}</span>
              {!authConfigured && <span>Backend auth not configured.</span>}
            </div>
          </div>
        </section>
      </main>
    );
  }

  // ── Main chat layout ───────────────────────────────────────────────────
  return (
    <div className="chatRoot">
      {/* Desktop sidebar — hidden on mobile via CSS */}
      <Sidebar
        userInitials={userInitials}
        apiBase={API_BASE}
        authHeaders={authHeaders}
        userId={userId}
        workspaceId={workspaceId}
        onSignOut={signOut}
      />

      {/* Mobile top bar + drawer — hidden on desktop via CSS */}
      <MobileNav
        activeThreadTitle={activeThreadTitle}
        userInitials={userInitials}
        userEmail={userEmail}
        apiBase={API_BASE}
        authHeaders={authHeaders}
        userId={userId}
        workspaceId={workspaceId}
        onSignOut={signOut}
      />

      {/* Main content column */}
      <div className="chatMain">
        <MessageList
          apiBase={API_BASE}
          authHeaders={authHeaders}
          userId={userId}
          workspaceId={workspaceId}
        />
        <Composer
          apiBase={API_BASE}
          authHeaders={authHeaders}
          userId={userId}
          workspaceId={workspaceId}
        />
      </div>

      {/* Per-message insights drawer — overlays everything */}
      <InsightsDrawer
        apiBase={API_BASE}
        authHeaders={authHeaders}
        userId={userId}
        workspaceId={workspaceId}
      />
    </div>
  );
}
