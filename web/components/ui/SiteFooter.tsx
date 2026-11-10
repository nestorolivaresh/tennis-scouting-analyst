import styles from "./SiteFooter.module.css";

export function SiteFooter() {
  return (
    <footer className={`on-green ${styles.footer}`}>
      <div className="stripe" aria-hidden="true" />
      <div className={styles.inner}>
        <p className={styles.credits}>
          Matches 2015 to 2025 and player details adapted from “Tennis databases, files, and algorithms” by Jeff Sackmann /{" "}
          <a href="https://www.tennisabstract.com/">Tennis Abstract</a>, under{" "}
          <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a>. Season 2026:{" "}
          <a href="https://stats.tennismylife.org/tennis-match-database">TennisMyLife ATP match database</a>, for
          non-commercial use. A non-commercial project; full terms in DATA_LICENSE.md.
        </p>
      </div>
    </footer>
  );
}
