// frontend/app/i18n.tsx
"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Lang = "en" | "fr" | "es" | "pcm" | "ar";
export const LANGS: { code: Lang; label: string }[] = [
  { code: "en", label: "English" },
  { code: "fr", label: "Français" },
  { code: "es", label: "Español" },
  { code: "pcm", label: "Pidgin" },
  { code: "ar", label: "العربية" },
];

// UI chrome strings. Backend responses are already multilingual; this localises
// the app shell so it never feels English-only or robotic.
type Dict = Record<string, string>;
const STRINGS: Record<Lang, Dict> = {
  en: {
    appName: "JimsAI", newChat: "New chat", send: "Send", stop: "Stop", attach: "Attach file",
    messageInput: "Message input", composerPlaceholder: "Ask JimsAI anything — code, math, science…",
    canvasRoute: "Canvas route", inventionRoute: "Invention route",
    groundedNote: "Grounded answers — verified, no LLM in the answer path.",
    copy: "Copy", copied: "Copied", edit: "Edit", regenerate: "Regenerate",
    goodResponse: "Good response", badResponse: "Bad response", insights: "Insights",
    thinking: "JimsAI is working…", emptyTitle: "How can I help?",
    emptySubtitle: "Ask anything — code, math, science, or teach me about your workspace. Answers are grounded and verified.",
    grounded: "Grounded · no LLM", viaModel: "via model", gaps: "gaps", confidence: "confidence",
    signIn: "Sign in", signOut: "Sign out", createAccount: "Create account", email: "Email", password: "Password",
    signInTitle: "Sign in to JimsAI", signInSub: "Persistent memory, feedback and training need a workspace identity.",
    theme: "Theme", light: "Light", dark: "Dark", system: "System", language: "Language",
    deleteThread: "Delete chat", runtimeReady: "Runtime ready", runtimeUnavailable: "Runtime unavailable", checkingRuntime: "Checking runtime…",
  },
  fr: {
    appName: "JimsAI", newChat: "Nouvelle discussion", send: "Envoyer", stop: "Arrêter", attach: "Joindre un fichier",
    messageInput: "Saisie du message", composerPlaceholder: "Demandez tout à JimsAI — code, maths, science…",
    canvasRoute: "Route canvas", inventionRoute: "Route invention",
    groundedNote: "Réponses fondées — vérifiées, sans LLM dans la réponse.",
    copy: "Copier", copied: "Copié", edit: "Modifier", regenerate: "Régénérer",
    goodResponse: "Bonne réponse", badResponse: "Mauvaise réponse", insights: "Analyses",
    thinking: "JimsAI travaille…", emptyTitle: "Comment puis-je aider ?",
    emptySubtitle: "Demandez tout — code, maths, science, ou apprenez-moi votre espace. Réponses fondées et vérifiées.",
    grounded: "Fondé · sans LLM", viaModel: "via modèle", gaps: "lacunes", confidence: "confiance",
    signIn: "Se connecter", signOut: "Se déconnecter", createAccount: "Créer un compte", email: "E-mail", password: "Mot de passe",
    signInTitle: "Connexion à JimsAI", signInSub: "La mémoire, le feedback et l'entraînement exigent une identité d'espace.",
    theme: "Thème", light: "Clair", dark: "Sombre", system: "Système", language: "Langue",
    deleteThread: "Supprimer", runtimeReady: "Service prêt", runtimeUnavailable: "Service indisponible", checkingRuntime: "Vérification…",
  },
  es: {
    appName: "JimsAI", newChat: "Nuevo chat", send: "Enviar", stop: "Detener", attach: "Adjuntar archivo",
    messageInput: "Entrada de mensaje", composerPlaceholder: "Pregunta a JimsAI — código, matemáticas, ciencia…",
    canvasRoute: "Ruta canvas", inventionRoute: "Ruta invención",
    groundedNote: "Respuestas fundamentadas — verificadas, sin LLM en la respuesta.",
    copy: "Copiar", copied: "Copiado", edit: "Editar", regenerate: "Regenerar",
    goodResponse: "Buena respuesta", badResponse: "Mala respuesta", insights: "Análisis",
    thinking: "JimsAI está trabajando…", emptyTitle: "¿En qué puedo ayudar?",
    emptySubtitle: "Pregunta lo que sea — código, matemáticas, ciencia, o enséñame tu espacio. Respuestas fundamentadas y verificadas.",
    grounded: "Fundamentado · sin LLM", viaModel: "vía modelo", gaps: "lagunas", confidence: "confianza",
    signIn: "Iniciar sesión", signOut: "Cerrar sesión", createAccount: "Crear cuenta", email: "Correo", password: "Contraseña",
    signInTitle: "Inicia sesión en JimsAI", signInSub: "La memoria, el feedback y el entrenamiento requieren identidad de espacio.",
    theme: "Tema", light: "Claro", dark: "Oscuro", system: "Sistema", language: "Idioma",
    deleteThread: "Eliminar", runtimeReady: "Servicio listo", runtimeUnavailable: "Servicio no disponible", checkingRuntime: "Comprobando…",
  },
  pcm: {
    appName: "JimsAI", newChat: "New chat", send: "Send am", stop: "Stop", attach: "Attach file",
    messageInput: "Message box", composerPlaceholder: "Ask JimsAI anytin — code, maths, science…",
    canvasRoute: "Canvas road", inventionRoute: "Invention road",
    groundedNote: "Answer wey get ground — dem check am, no LLM for di answer.",
    copy: "Copy", copied: "Don copy", edit: "Edit", regenerate: "Do am again",
    goodResponse: "Correct answer", badResponse: "Bad answer", insights: "Wetin dey inside",
    thinking: "JimsAI dey work…", emptyTitle: "How I fit help you?",
    emptySubtitle: "Ask anytin — code, maths, science, or teach me about your work. Di answer dey ground and dem check am.",
    grounded: "Ground · no LLM", viaModel: "with model", gaps: "gap", confidence: "confidence",
    signIn: "Sign in", signOut: "Comot", createAccount: "Open account", email: "Email", password: "Password",
    signInTitle: "Sign in to JimsAI", signInSub: "Memory, feedback and training need workspace identity.",
    theme: "Theme", light: "Light", dark: "Dark", system: "System", language: "Language",
    deleteThread: "Delete", runtimeReady: "System ready", runtimeUnavailable: "System no dey", checkingRuntime: "Dey check…",
  },
  ar: {
    appName: "JimsAI", newChat: "محادثة جديدة", send: "إرسال", stop: "إيقاف", attach: "إرفاق ملف",
    messageInput: "حقل الرسالة", composerPlaceholder: "اسأل JimsAI أي شيء — برمجة، رياضيات، علوم…",
    canvasRoute: "مسار كانفاس", inventionRoute: "مسار الابتكار",
    groundedNote: "إجابات موثوقة — مُتحقَّق منها، بدون نموذج لغوي في مسار الإجابة.",
    copy: "نسخ", copied: "تم النسخ", edit: "تعديل", regenerate: "إعادة توليد",
    goodResponse: "إجابة جيدة", badResponse: "إجابة سيئة", insights: "تحليلات",
    thinking: "‏JimsAI يعمل…", emptyTitle: "كيف أساعدك؟",
    emptySubtitle: "اسأل أي شيء — برمجة، رياضيات، علوم، أو علّمني عن مساحتك. الإجابات موثوقة ومُتحقَّق منها.",
    grounded: "موثوق · بدون نموذج", viaModel: "عبر نموذج", gaps: "فجوات", confidence: "الثقة",
    signIn: "تسجيل الدخول", signOut: "تسجيل الخروج", createAccount: "إنشاء حساب", email: "البريد", password: "كلمة المرور",
    signInTitle: "تسجيل الدخول إلى JimsAI", signInSub: "الذاكرة والتقييم والتدريب تتطلب هوية مساحة عمل.",
    theme: "السمة", light: "فاتح", dark: "داكن", system: "النظام", language: "اللغة",
    deleteThread: "حذف", runtimeReady: "الخدمة جاهزة", runtimeUnavailable: "الخدمة غير متاحة", checkingRuntime: "جارٍ التحقق…",
  },
};

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: string) => string; dir: "ltr" | "rtl" };
const I18nContext = createContext<Ctx | null>(null);

function detectLang(): Lang {
  if (typeof window === "undefined") return "en";
  const saved = window.localStorage.getItem("jimsai:lang") as Lang | null;
  if (saved && STRINGS[saved]) return saved;
  const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
  return (["en", "fr", "es", "ar"].includes(nav) ? nav : "en") as Lang;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    setLangState(detectLang());
  }, []);

  const dir: "ltr" | "rtl" = lang === "ar" ? "rtl" : "ltr";

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { window.localStorage.setItem("jimsai:lang", l); } catch {}
  }, []);

  const t = useCallback((k: string) => STRINGS[lang][k] ?? STRINGS.en[k] ?? k, [lang]);

  const value = useMemo(() => ({ lang, setLang, t, dir }), [lang, setLang, t, dir]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) return { lang: "en", setLang: () => {}, t: (k) => STRINGS.en[k] ?? k, dir: "ltr" };
  return ctx;
}
