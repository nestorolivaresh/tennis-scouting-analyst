"use client";

// The language for everything under it. The server picks the first one (app/layout.tsx, D-027).
// A switch saves the choice in a cookie and re-renders in place, so a report or a chat on screen
// stays where it is; only the page title needs the server, so the route is refreshed for it.

import { useRouter } from "next/navigation";
import { type ReactNode, createContext, useContext, useState } from "react";
import { EN, type Locale, MESSAGES, type T, localeCookie } from "@/lib/i18n.ts";

type Language = { locale: Locale; t: T; setLocale: (next: Locale) => void };

const LanguageContext = createContext<Language>({ locale: "en", t: EN, setLocale: () => {} });

export function LanguageProvider({ initial, children }: { initial: Locale; children: ReactNode }) {
  const router = useRouter();
  const [locale, setState] = useState<Locale>(initial);

  function setLocale(next: Locale) {
    if (next === locale) return;
    document.cookie = localeCookie(next, window.location.protocol === "https:");
    document.documentElement.lang = next;
    setState(next);
    router.refresh();
  }

  return <LanguageContext value={{ locale, t: MESSAGES[locale], setLocale }}>{children}</LanguageContext>;
}

export function useLanguage(): Language {
  return useContext(LanguageContext);
}

export function useT(): T {
  return useContext(LanguageContext).t;
}
