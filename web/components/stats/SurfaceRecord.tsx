import { useT } from "@/components/ui/LanguageProvider.tsx";
import { type PageQuery, type PlayerStats, type SurfaceTileId, countedNote, surfaceTiles } from "@/lib/player-stats.ts";
import styles from "./Stats.module.css";

export function SurfaceRecord({ data, query, onPick }: { data: PlayerStats; query: PageQuery; onPick: (tile: SurfaceTileId) => void }) {
  const t = useT();
  return (
    <section className={styles.sec} aria-labelledby="by-surface">
      <h2 id="by-surface" className="h2">{t.recordBySurface}</h2>
      <div className="courtline" aria-hidden="true" />
      <p className={styles.note}>{t.chooseSurface}</p>
      <fieldset className={styles.surfaceSet}>
        <legend className="vh">{t.filterBySurface}</legend>
        <div className={styles.surfaces}>
          {surfaceTiles(data.by_surface, query, t).map((tile) => (
            <label key={tile.id} className={styles.surf}>
              <input type="radio" name="surface" value={tile.id} checked={tile.on} onChange={() => onPick(tile.id)} />
              <span className={`${styles.court} ${tile.swatch}`}>
                <svg aria-hidden="true" width="100%" height="100%" viewBox="0 0 240 132" preserveAspectRatio="none" fill="none" stroke="#FFFFFF" strokeWidth="2.4">
                  <line x1="0" y1="16" x2="240" y2="16" />
                  <line x1="214" y1="0" x2="214" y2="132" />
                </svg>
                <span className={`${styles.surfRate}${tile.hasRate ? "" : ` ${styles.surfNone}`}`}>{tile.rate}</span>
                {tile.on && <span className={styles.ball} aria-hidden="true" />}
              </span>
              <span className={styles.surfFoot}>
                <span className={styles.surfName}>{tile.name}</span>
                <span className={styles.surfRecord}>{tile.record}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <p className={`${styles.note} ${styles.countedNote}`}>{countedNote(data.record, data.profile.player.name, t)}</p>
    </section>
  );
}
