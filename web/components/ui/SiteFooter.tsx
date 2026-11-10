"use client";

import { useT } from "./LanguageProvider.tsx";
import styles from "./SiteFooter.module.css";

export function SiteFooter() {
  const t = useT();
  return (
    <footer className={`on-green ${styles.footer}`}>
      <div className="stripe" aria-hidden="true" />
      <div className={styles.inner}>
        <p className={styles.credits}>
          {t.footerSource}{" "}
          <a href="https://www.tennisabstract.com/">Tennis Abstract</a>, {t.footerUnder}{" "}
          <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a>. {t.footerSeason}{" "}
          <a href="https://stats.tennismylife.org/tennis-match-database">{t.footerTml}</a>, {t.footerEnd}
        </p>
      </div>
    </footer>
  );
}
