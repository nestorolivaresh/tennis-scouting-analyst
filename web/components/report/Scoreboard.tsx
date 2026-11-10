import type { CSSProperties } from "react";
import { Board } from "@/components/ui/Board.tsx";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { Medal } from "@/components/ui/Medal.tsx";
import { type ScoreboardRow, type Tile, dataThrough, isSmallSample, isTwoYearWindow, matchCount, meetingCount, scoreboardTiles } from "@/lib/evidence.ts";
import { surfaceWords } from "@/lib/i18n.ts";
import { longDate } from "@/lib/people.ts";
import type { PlayerRef, ReportResponse } from "@/lib/types.ts";
import styles from "./ReportView.module.css";

type Labels = { career: string; onSurface: string; winRate: string; windowWords: string };

export function Scoreboard({ data, countries }: { data: ReportResponse; countries: Record<number, string | null> }) {
  const t = useT();
  const { player, opponent, surface } = data.request;
  const word = surface.toLowerCase();
  const words = surfaceWords(t, surface);
  const tiles = scoreboardTiles(data.evidence, player, opponent, surface, data.request, t);
  const through = dataThrough(data.evidence);
  const labels: Labels = {
    career: t.careerHeadToHead,
    onSurface: t.headToHeadOn(words),
    winRate: t.surfaceWinRate(words),
    windowWords: isTwoYearWindow(data.request) ? t.lastTwoYears : "",
  };
  return (
    <Board aria-labelledby="sb-title" className={styles.board}>
      <div className={styles.slats}>
        <div className={`slat ${styles.titleSlat}`}>
          <h1 id="sb-title" className={styles.title}>{t.scoutingTitle(opponent.name, player.name)}</h1>
          <div className={styles.titleMeta}>
            <span className={styles.onSurface}><span className={`sw sw-${word} ${styles.swatch}`} aria-hidden="true" />{words.onCap}</span>
            {through && <span>{t.dataThrough(longDate(through, t))}</span>}
          </div>
        </div>

        {/* Each tile carries its own label for screen readers, so this row is only for the eye. */}
        <div className={`slat ${styles.grid} ${styles.heads}`} aria-hidden="true">
          <span />
          <span>{labels.career}</span>
          <span>{labels.onSurface}</span>
          <span>{labels.winRate}{labels.windowWords}</span>
        </div>

        <PlayerRow who={player} role={t.yourPlayer} tone="player" country={countries[player.player_id]} tiles={tiles.player} labels={labels} turns={["t-a", "t-b", "t-c"]} delays={[0.05, 0.14, 0.23]} />
        <PlayerRow who={opponent} role={t.opponent} tone="opponent" country={countries[opponent.player_id]} tiles={tiles.opponent} labels={labels} turns={["t-b", "t-c", "t-a"]} delays={[0.32, 0.41, 0.5]} />
      </div>
    </Board>
  );
}

type RowProps = {
  who: PlayerRef;
  role: string;
  tone: "player" | "opponent";
  country: string | null | undefined;
  tiles: ScoreboardRow;
  labels: Labels;
  turns: string[];
  delays: number[];
};

function PlayerRow({ who, role, tone, country, tiles, labels, turns, delays }: RowProps) {
  const t = useT();
  const meetings = (n: number) => meetingCount(n, t);
  return (
    <div className={`slat ${styles.grid} ${styles.playerRow}`}>
      <div className={styles.name}>
        {/* The phone size comes from the board's custom properties, not a second medal. */}
        <Medal name={who.name} country={country} tone={tone} />
        <div className={styles.nameText}>
          <div className={styles.fullName}>{who.name}</div>
          <div className={styles.role}>{role}</div>
        </div>
      </div>
      <TileCell tile={tiles.career} label={labels.career} sampleText={meetings} turn={turns[0]} delay={delays[0]} />
      <TileCell tile={tiles.onSurface} label={labels.onSurface} sampleText={meetings} turn={turns[1]} delay={delays[1]} />
      <TileCell tile={tiles.winRate} label={labels.winRate} rest={labels.windowWords} sampleText={(n) => matchCount(n, t)} turn={turns[2]} delay={delays[2]} wide />
    </div>
  );
}

type CellProps = {
  tile: Tile;
  label: string;
  rest?: string;
  sampleText: (n: number) => string;
  turn: string;
  delay: number;
  wide?: boolean;
};

function TileCell({ tile, label, rest = "", sampleText, turn, delay, wide = false }: CellProps) {
  const t = useT();
  const sizing = tile.status !== "ok" ? styles.tileWord : wide ? styles.tileSmall : "";
  const style: CSSProperties = { animationDelay: `${delay}s` };
  return (
    <div className="tile-cell">
      <span className="vh">{label}{rest}: </span>
      <span className="tile-label" aria-hidden="true">{label}<span className={styles.labelRest}>{rest}</span></span>
      <span className={`tile ${turn} ${sizing}`} style={style}>{tile.text}</span>
      {tile.sample !== null && <span className={styles.tileSample}>{sampleText(tile.sample)}</span>}
      {isSmallSample(tile.sample) && <span className={`tag ${styles.tagOnGreen}`}>{t.smallSample}</span>}
    </div>
  );
}
