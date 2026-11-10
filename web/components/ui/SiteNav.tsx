"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLanguage } from "@/components/ui/LanguageProvider.tsx";
import { BACK_TO_SETUP } from "@/lib/handoff.ts";
import { LOCALES, LOCALE_NAMES } from "@/lib/i18n.ts";
import styles from "./SiteNav.module.css";

export function SiteNav() {
  const pathname = usePathname();
  const { t, locale, setLocale } = useLanguage();
  const sections = [
    { href: "/", label: t.navScouting, current: pathname === "/" },
    { href: "/players", label: t.navPlayers, current: pathname === "/players" || pathname.startsWith("/players/") },
  ];
  // A link to the current route does nothing by itself, but the report and the loader live on
  // "/" too, so the page is told to go back to match setup.
  const toSetup = (href: string) => () => {
    if (href === "/" && pathname === "/") window.dispatchEvent(new Event(BACK_TO_SETUP));
  };
  return (
    <div>
      <div className="stripe" aria-hidden="true" />
      <header className={styles.site}>
        <Link href="/" aria-label="Tennis Scouting Analyst" className={styles.brand} onClick={toSetup("/")}>
          <svg className={styles.emblem} width="28" height="42" viewBox="0 0 30 44" aria-hidden="true" fill="none" stroke="#12372B" strokeWidth="1.6">
            <rect x="1" y="1" width="28" height="42" />
            <line x1="5" y1="1" x2="5" y2="43" />
            <line x1="25" y1="1" x2="25" y2="43" />
            <line x1="5" y1="11" x2="25" y2="11" />
            <line x1="5" y1="33" x2="25" y2="33" />
            <line x1="15" y1="11" x2="15" y2="33" />
            <line className={styles.net} x1="0" y1="22" x2="30" y2="22" stroke="#A8843F" strokeWidth="2.6" />
          </svg>
          <span className={styles.brandName}>Tennis Scouting Analyst</span>
        </Link>
        <div className={styles.right}>
          <nav aria-label={t.navMain} className={styles.nav}>
            {sections.map(({ href, label, current }) => (
              <Link key={href} href={href} className={styles.link} aria-current={current ? "page" : undefined} onClick={toSetup(href)}>
                {current && <span className="serve" aria-hidden="true" />}
                {label}
              </Link>
            ))}
          </nav>
          {/* Each language is named in itself, so anyone can find their own. */}
          <div className={styles.languages} role="group" aria-label={t.language}>
            {LOCALES.map((code) => (
              <button
                key={code}
                type="button"
                lang={code}
                className={styles.language}
                aria-pressed={code === locale}
                aria-label={LOCALE_NAMES[code]}
                title={LOCALE_NAMES[code]}
                onClick={() => setLocale(code)}
              >
                {code.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </header>
    </div>
  );
}
