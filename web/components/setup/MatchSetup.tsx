"use client";

// Match setup: your player and the opponent feed a draw bracket into the surface. The choices
// live in the page, so they survive a failed report.

import { PlayerSearch } from "@/components/ui/PlayerSearch.tsx";
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
  const ready = player !== null && opponent !== null && player.player_id !== opponent.player_id;

  return (
    <main className={styles.main}>
      <div className={styles.intro}>
        <h1 className={styles.title}>Scout the next opponent</h1>
        <p className={styles.lede}>ATP tour-level singles, 2015 on. Numbers come from tested stats tools, not the model’s memory.</p>
      </div>

      {error !== null && (
        <p className={styles.alert} role="alert">
          <strong>The report couldn't be written.</strong> {error}
        </p>
      )}

      <form className={styles.card} aria-labelledby="setup-title" onSubmit={(event) => event.preventDefault()}>
        <h2 id="setup-title" className={styles.cardTitle}>Set up the match</h2>
        <p className={styles.cardLede}>Pick your player and who they're facing. We'll scout the opponent and write a game plan for your player.</p>

        <div className={styles.draw}>
          <div className={styles.players}>
            <PlayerLine
              id="your-player"
              label="Your player"
              help="The player you're preparing."
              tone="player"
              value={player}
              onChange={onPlayer}
              excludeId={opponent?.player_id}
            />
            <PlayerLine
              id="opponent"
              label="Opponent"
              help="The player we'll scout."
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
            <legend>Surface</legend>
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
                  <span className={styles.courtName}>{name}</span>
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
                  We'll scout <strong>{opponent.name}</strong> on {surface.toLowerCase()} and write the game plan for <strong>{player.name}</strong>.
                </p>
                <p className={styles.goNote}>Uses the two years up to the newest tournament in the data. It takes 15 to 40 seconds.</p>
              </>
            ) : (
              <p className={styles.goLine}>{nextStep(player, opponent)}</p>
            )}
          </div>
          <div className={styles.goAction}>
            <button type="button" className="btn btn-wide" disabled={!ready} onClick={onStart}>
              Write the report
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}

function nextStep(player: Candidate | null, opponent: Candidate | null): string {
  if (!player && !opponent) return "Choose your player to start.";
  if (player && !opponent) return `Now choose who ${player.name} is facing.`;
  return "Now choose your player.";
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
          placeholder="Search by name"
          excludeId={excludeId}
          tone={tone}
          changeLabel={`Change ${label.toLowerCase()}`}
        />
      </div>
    </div>
  );
}
