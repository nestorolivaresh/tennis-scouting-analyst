// The app's languages. The default is the visitor's saved choice, then the first of their
// browser's languages that the app has, then English. No location or IP is used (D-027).

import { en, type Messages } from "./messages/en.ts";
import { es } from "./messages/es.ts";
import type { Locale, SurfaceWords } from "./messages/format.ts";
import { fr } from "./messages/fr.ts";

export type { Locale, SurfaceWords };
export type T = Messages;

export const LOCALES: Locale[] = ["en", "es", "fr"];
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", es: "Español", fr: "Français" };
export const LOCALE_COOKIE = "lang";
export const EN: T = en;
export const MESSAGES: Record<Locale, T> = { en, es, fr };

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as string[]).includes(value);
}

/** The saved choice when it is one of ours, then the browser's languages by preference (q-value,
 * then order), matched on the base language ("es-419" is Spanish), then English. */
export function pickLocale(saved: string | null | undefined, acceptLanguage: string | null | undefined): Locale {
  if (isLocale(saved)) return saved;
  const ranked = (acceptLanguage ?? "")
    .split(",")
    .map((part, index) => {
      const [tag, ...params] = part.trim().split(";");
      const q = params.map((p) => p.trim()).find((p) => p.startsWith("q="));
      const quality = q === undefined ? 1 : Number(q.slice(2));
      return { base: tag.trim().toLowerCase().split("-")[0], quality: Number.isFinite(quality) ? quality : 0, index };
    })
    .filter((entry) => entry.base && entry.quality > 0)
    .sort((a, b) => b.quality - a.quality || a.index - b.index);
  return ranked.map((entry) => entry.base).find(isLocale) ?? "en";
}

/** The cookie that keeps a visitor's choice for a year. It holds only the language code. */
export function localeCookie(locale: Locale, secure: boolean): string {
  return `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax${secure ? "; Secure" : ""}`;
}

/** How a surface from the data reads in this language; an unknown one is shown as the data has it. */
export function surfaceWords(t: T, raw: string): SurfaceWords {
  const known = t.surfaces[raw];
  if (known) return known;
  const lower = raw.toLowerCase();
  return { name: raw, lower, on: lower, onCap: raw, courts: lower, courtsCap: raw };
}

/** An API failure in this language when its kind is known, otherwise the API's own message. */
export function failureText(kind: string, message: string, t: T): string {
  return t.errors[kind] ?? message;
}

/** One of the API's fixed messages (a stopped run, for example) in this language. */
export function serverText(message: string, t: T): string {
  return t.serverMessages[message] ?? message;
}
