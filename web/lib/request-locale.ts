// The language for a page request, on the server: the saved cookie, then Accept-Language (D-027).
// Reading them makes pages render per request, which is what keeps each visitor's language right
// in the first HTML, with no flash of English.

import { cookies, headers } from "next/headers";
import { LOCALE_COOKIE, type Locale, pickLocale } from "./i18n.ts";

export async function requestLocale(): Promise<Locale> {
  const [jar, head] = await Promise.all([cookies(), headers()]);
  return pickLocale(jar.get(LOCALE_COOKIE)?.value, head.get("accept-language"));
}
