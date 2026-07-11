"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelRightClose, PanelRightOpen } from "lucide-react";

import { AUTH_STATE_EVENT, supabaseUserContext } from "./authHeaders";

export default function AppNav() {
  const pathname = usePathname();
  const isChat = pathname === "/" || pathname.startsWith("/user") || pathname.startsWith("/chat");
  const [insightsOpen, setInsightsOpen] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  // Training is engineer/admin-only; normal users only ever see Chat.
  const items = [
    { href: "/user" as const, label: "Chat", active: isChat },
    ...(isAdmin
      ? [{ href: "/training" as const, label: "Training", active: pathname.startsWith("/training") }]
      : []),
  ];

  useEffect(() => {
    function updateAuthState() {
      const ctx = supabaseUserContext();
      setAuthenticated(ctx.authenticated);
      setIsAdmin(ctx.isAdmin);
    }

    updateAuthState();
    window.addEventListener(AUTH_STATE_EVENT, updateAuthState);
    window.addEventListener("storage", updateAuthState);
    return () => {
      window.removeEventListener(AUTH_STATE_EVENT, updateAuthState);
      window.removeEventListener("storage", updateAuthState);
    };
  }, []);

  useEffect(() => {
    function updateInsightState(event: Event) {
      const nextState = (event as CustomEvent<{ open: boolean }>).detail?.open;
      if (typeof nextState === "boolean") setInsightsOpen(nextState);
    }

    window.addEventListener("jimsai:insights-state", updateInsightState);
    return () => window.removeEventListener("jimsai:insights-state", updateInsightState);
  }, []);

  if (!authenticated) return null;

  return (
    <div className="headerControls">
      <nav className="navLinks" aria-label="Primary">
        {items.map((item) => (
          <Link className={item.active ? "active" : ""} href={item.href} key={item.href} aria-current={item.active ? "page" : undefined}>
            {item.label}
          </Link>
        ))}
      </nav>
      {isChat ? (
        <button
          className="iconButton compact"
          type="button"
          title={insightsOpen ? "Close insight panel" : "Open insight panel"}
          onClick={() => window.dispatchEvent(new Event("jimsai:toggle-insights"))}
        >
          {insightsOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
        </button>
      ) : null}
    </div>
  );
}
