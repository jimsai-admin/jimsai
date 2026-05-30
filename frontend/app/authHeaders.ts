"use client";

const CUSTOM_SESSION_KEY = "jimsai.supabase.session";

export function supabaseAuthHeaders(): Record<string, string> {
  const token = supabaseAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function supabaseAuthConfigured(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
}

export function storeSupabaseSession(payload: Record<string, unknown>) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(CUSTOM_SESSION_KEY, JSON.stringify(payload));
}

export function clearSupabaseSession() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(CUSTOM_SESSION_KEY);
}

export async function refreshSupabaseSession(apiBase: string): Promise<boolean> {
  const refreshToken = supabaseRefreshToken();
  if (!refreshToken) {
    clearSupabaseSession();
    return false;
  }
  try {
    const response = await fetch(`${apiBase}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken })
    });
    const data = (await response.json()) as Record<string, unknown>;
    if (!response.ok) throw new Error(String(data.detail ?? data.msg ?? data.error_description ?? data.error ?? "refresh failed"));
    storeSupabaseSession(data);
    return true;
  } catch {
    clearSupabaseSession();
    return false;
  }
}

export function supabaseAuthUrl(path: string): string {
  const base = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").trim().replace(/\/rest\/v1\/?$/, "").replace(/\/auth\/v1\/?$/, "").replace(/\/$/, "");
  return `${base}/auth/v1/${path.replace(/^\//, "")}`;
}

export function supabaseAnonKey(): string {
  return process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";
}

export function supabaseUserContext(): { userId: string; workspaceId: string | null; authenticated: boolean } {
  const session = supabaseSessionPayload();
  const user = session?.currentSession?.user ?? session?.session?.user ?? session?.user;
  const id = typeof user?.id === "string" ? user.id : "";
  if (!id) return { userId: "anonymous-browser", workspaceId: null, authenticated: false };
  return { userId: `supabase:${id}`, workspaceId: `workspace:${id}`, authenticated: true };
}

function supabaseAccessToken(): string {
  const session = supabaseSessionPayload();
  return session?.currentSession?.access_token ?? session?.session?.access_token ?? session?.access_token ?? "";
}

function supabaseRefreshToken(): string {
  const session = supabaseSessionPayload();
  return session?.currentSession?.refresh_token ?? session?.session?.refresh_token ?? session?.refresh_token ?? "";
}

function supabaseSessionPayload(): {
  access_token?: string;
  refresh_token?: string;
  currentSession?: { access_token?: string; refresh_token?: string; user?: { id?: string } };
  session?: { access_token?: string; refresh_token?: string; user?: { id?: string } };
  user?: { id?: string };
} | null {
  if (typeof window === "undefined") return null;
  const custom = accessTokenFromStorageValue(window.localStorage.getItem(CUSTOM_SESSION_KEY));
  if (custom) return custom;
  const configuredUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  const keys = supabaseStorageKeys(configuredUrl);
  for (const key of keys) {
    const payload = accessTokenFromStorageValue(window.localStorage.getItem(key));
    if (payload) return payload;
  }
  return null;
}

function supabaseStorageKeys(configuredUrl: string): string[] {
  const keys = new Set<string>();
  try {
    const projectRef = new URL(configuredUrl).hostname.split(".")[0];
    if (projectRef) keys.add(`sb-${projectRef}-auth-token`);
  } catch {
    // Ignore invalid env at render time; the API will reject unauthenticated calls.
  }
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (key?.startsWith("sb-") && key.endsWith("-auth-token")) keys.add(key);
  }
  return [...keys];
}

function accessTokenFromStorageValue(value: string | null): {
  access_token?: string;
  refresh_token?: string;
  currentSession?: { access_token?: string; refresh_token?: string; user?: { id?: string } };
  session?: { access_token?: string; refresh_token?: string; user?: { id?: string } };
  user?: { id?: string };
} | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as {
      access_token?: string;
      refresh_token?: string;
      currentSession?: { access_token?: string; refresh_token?: string; user?: { id?: string } };
      session?: { access_token?: string; refresh_token?: string; user?: { id?: string } };
      user?: { id?: string };
    };
    return parsed.currentSession?.access_token || parsed.session?.access_token || parsed.access_token ? parsed : null;
  } catch {
    return null;
  }
}
