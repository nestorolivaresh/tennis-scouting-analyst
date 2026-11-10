"use client";

// Match setup: your player and the opponent feed a draw bracket into the surface. The choices
// live in the page, so they survive a failed report.

import { useT } from "@/components/ui/LanguageProvider.tsx";
import { PlayerSearch } from "@/components/ui/PlayerSearch.tsx";
import { type T, surfaceWords } from "@/lib/i18n.ts";
import type { Candidate, Surface } from "@/lib/types.ts";
import styles from "./MatchSetup.module.css";

const COURTS: { name: Surface; swatch: string }[] = [
  { name: "Clay", swatch: "sw-clay" },
  { name: "Grass", swatch: "sw-grass" },
  { name: "Hard", swatch: "sw-hard" },
];

export type MatchSetupProps = {
  player: Candidate | null;
  opponent: Candidate | null;
  surface: Surface;
  onPlayer: (candidate: Candidate | null) => void;
  onOpponent: (candidate: Candidate | null) => void;
  onSurface: (surface: Surface) => void;
  onStart: () => void;
  /** The API's message from the last attempt, when it failed. */
  error: string | null;
};

export function MatchSetup({ player, opponent, surface, onPlayer, onOpponent, onSurface, onStart, error }: MatchSetupProps) {
  const t = useT();
  const ready = player !== null && opponent !== null && player.player_id !== opponent.player_id;
  const [scout, writeFor, end] = t.setupReady(surfaceWords(t, surface));

  return (
    <main className={styles.main}>
      <div className={styles.intro}>
        <h1 className={styles.title}>{t.setupTitle}</h1>
        <p className={styles.lede}>{t.setupLede}</p>
      </div>

      {error !== null && (
        <p className={styles.alert} role="alert">
          <strong>{t.reportNotWritten}</strong> {error}
        </p>
      )}

      <form className={styles.card} aria-labelledby="setup-title" onSubmit={(event) => event.preventDefault()}>
        <h2 id="setup-title" className={styles.cardTitle}>{t.setupCardTitle}</h2>
        <p className={styles.cardLede}>{t.setupCardLede}</p>

        <div className={styles.draw}>
          <div className={styles.players}>
            <PlayerLine
              id="your-player"
              label={t.yourPlayer}
              help={t.yourPlayerHelp}
              tone="player"
              value={player}
              onChange={onPlayer}
              excludeId={opponent?.player_id}
            />
            <PlayerLine
              id="opponent"
              label={t.opponent}
              help={t.opponentHelp}
              tone="opponent"
              value={opponent}
              onChange={onOpponent}
              excludeId={player?.player_id}
            />
          </div>

          <div className={styles.bracket} aria-hidden="true">
            <span className={styles.bracketTop} />
            <span className={styles.bracketBottom} />
            <span className={styles.bracketSpine} />
            <span className={styles.bracketOut} />
          </div>

          <fieldset className={styles.surface}>
            <legend>{t.surfaceLegend}</legend>
            <div className={styles.courts}>
              {COURTS.map(({ name, swatch }) => (
                <label key={name} className={styles.swatch}>
                  <input type="radio" name="surface" value={name} checked={surface === name} onChange={() => onSurface(name)} />
                  <span className={`${styles.court} ${swatch}`}>
                    <svg aria-hidden="true" width="100%" height="100%" viewBox="0 0 120 104" preserveAspectRatio="none" fill="none" stroke="#FFFFFF" strokeWidth="2.4">
                      <line x1="0" y1="20" x2="120" y2="20" />
                      <line x1="96" y1="0" x2="96" y2="104" />
                      <line x1="0" y1="72" x2="96" y2="72" />
                    </svg>
                    {surface === name && <span className={styles.ball} aria-hidden="true" />}
                  </span>
                  <span className={styles.courtName}>{surfaceWords(t, name).name}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <div className={styles.go}>
          <div className={styles.goText} role="status">
            {ready ? (
              <>
                <p className={styles.goLine}>
                  {scout}<strong>{opponent.name}</strong>{writeFor}<strong>{player.name}</strong>{end}
                </p>
                <p className={styles.goNote}>{t.setupReadyNote}</p>
              </>
            ) : (
              <p className={styles.goLine}>{nextStep(player, opponent, t)}</p>
            )}
          </div>
          <div className={styles.goAction}>
            <button type="button" className="btn btn-wide" disabled={!ready} onClick={onStart}>
              {t.writeReport}
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}

function nextStep(player: Candidate | null, opponent: Candidate | null, t: T): string {
  if (!player && !opponent) return t.chooseToStart;
  if (player && !opponent) return t.chooseWhoFacing(player.name);
  return t.chooseYourPlayer;
}

type PlayerLineProps = {
  id: string;
  label: string;
  help: string;
  tone: "player" | "opponent";
  value: Candidate | null;
  onChange: (candidate: Candidate | null) => void;
  excludeId: number | undefined;
};

function PlayerLine({ id, label, help, tone, value, onChange, excludeId }: PlayerLineProps) {
  const t = useT();
  const helpId = `${id}-help`;
  return (
    <div className={styles.line}>
      <label className={styles.lineLabel} htmlFor={id}>{label}</label>
      <span className={styles.lineHelp} id={helpId}>{help}</span>
      <div className={styles.search}>
        <PlayerSearch
          inputId={id}
          describedBy={helpId}
          value={value}
          onChange={onChange}
          placeholder={t.searchByName}
          excludeId={excludeId}
          tone={tone}
          changeLabel={t.changeWho(label)}
        />
      </div>
    </div>
  );
}
