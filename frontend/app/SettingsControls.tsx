// frontend/app/SettingsControls.tsx
"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Sun, Moon, Monitor, Globe } from "lucide-react";
import { LANGS, useI18n, type Lang } from "./i18n";

type ThemeMode = "light" | "dark" | "system";

function applyTheme(mode: ThemeMode) {
  const root = document.documentElement;
  if (mode === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", mode);
  try { window.localStorage.setItem("jimsai:theme", mode); } catch {}
}

function readTheme(): ThemeMode {
  if (typeof window === "undefined") return "system";
  return (window.localStorage.getItem("jimsai:theme") as ThemeMode) || "system";
}

export default function SettingsControls() {
  const { t, lang, setLang } = useI18n();
  const [mode, setMode] = useState<ThemeMode>("system");

  useEffect(() => {
    const m = readTheme();
    setMode(m);
    applyTheme(m);
  }, []);

  const choose = (m: ThemeMode) => { setMode(m); applyTheme(m); };

  const options: { key: ThemeMode; icon: ReactNode; label: string }[] = [
    { key: "light", icon: <Sun size={15} />, label: t("light") },
    { key: "dark", icon: <Moon size={15} />, label: t("dark") },
    { key: "system", icon: <Monitor size={15} />, label: t("system") },
  ];

  return (
    <div className="settingsControls">
      <div className="themeSwitch" role="group" aria-label={t("theme")}>
        {options.map((o) => (
          <button
            key={o.key}
            type="button"
            className={`themeSwitchBtn${mode === o.key ? " active" : ""}`}
            title={o.label}
            aria-pressed={mode === o.key}
            onClick={() => choose(o.key)}
          >
            {o.icon}
          </button>
        ))}
      </div>
      <label className="langSelect" title={t("language")}>
        <Globe size={15} />
        <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label={t("language")}>
          {LANGS.map((l) => (
            <option key={l.code} value={l.code}>{l.label}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
