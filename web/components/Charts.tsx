"use client";

// The report's two charts (spec): win rate by surface, and serve stats side by side. Both are
// drawn only from this run's tool results (lib/evidence.ts). A gap is a gap, with a note saying
// why (no matches, not looked up, or no matches with stats); it is never drawn as zero.

import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { type ChartData, type ServeRow, type SurfaceRow, type Window, serveChart, surfaceChart } from "@/lib/evidence.ts";
import type { Evidence, PlayerRef, Surface } from "@/lib/types.ts";

const PLAYER = "var(--player)";
const OPPONENT = "var(--opponent)";

type Props = { evidence: Evidence[]; player: PlayerRef; opponent: PlayerRef; surface: Surface; window: Window };

export function Charts({ evidence, player, opponent, surface, window }: Props) {
  const surfaces = surfaceChart(evidence, player, opponent, window);
  const serve = serveChart(evidence, player, opponent, surface, window);
  const legend = (
    <div className="legend" aria-hidden="true">
      <span style={{ color: PLAYER }}>{player.name}</span>
      <span style={{ color: OPPONENT }}>{opponent.name}</span>
    </div>
  );
  return (
    <div className="charts">
      <figure className="chart" style={{ margin: 0 }}>
        <h3>Win rate by surface</h3>
        {legend}
        <div className="chart-frame" role="img" aria-label={describeSurfaces(surfaces, player, opponent)}>
          <ResponsiveContainer>
            <BarChart data={surfaces.rows} margin={{ top: 20, right: 8, left: 0, bottom: 0 }} barGap={4} accessibilityLayer={false}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="surface" tickLine={false} axisLine={false} />
              <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} unit="%" tickLine={false} axisLine={false} width={48} />
              <Tooltip cursor={{ fill: "rgb(22 32 28 / 0.05)" }} content={<SurfaceTip player={player} opponent={opponent} />} />
              <Bar dataKey="player" name={player.name} fill={PLAYER} radius={[2, 2, 0, 0]}>
                <LabelList dataKey="player" position="top" formatter={label} fontSize={12} />
              </Bar>
              <Bar dataKey="opponent" name={opponent.name} fill={OPPONENT} radius={[2, 2, 0, 0]}>
                <LabelList dataKey="opponent" position="top" formatter={label} fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <Caption data={surfaces} note={`Tournaments starting ${window.date_from} to ${window.date_to}.`} />
      </figure>

      <figure className="chart" style={{ margin: 0 }}>
        <h3>Serve, return and break points, {serve.scope}</h3>
        {legend}
        <div className="chart-frame" style={{ height: 340 }} role="img" aria-label={describeServe(serve, player, opponent)}>
          <ResponsiveContainer>
            <BarChart data={serve.rows} layout="vertical" margin={{ top: 0, right: 40, left: 8, bottom: 0 }} barGap={2} accessibilityLayer={false}>
              <CartesianGrid horizontal={false} stroke="var(--line)" />
              <XAxis type="number" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} unit="%" tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="metric" width={150} tickLine={false} axisLine={false} fontSize={13} />
              <Tooltip cursor={{ fill: "rgb(22 32 28 / 0.05)" }} content={<ServeTip player={player} opponent={opponent} />} />
              <Bar dataKey="player" name={player.name} fill={PLAYER} barSize={9}>
                <LabelList dataKey="player" position="right" formatter={label} fontSize={11} />
              </Bar>
              <Bar dataKey="opponent" name={opponent.name} fill={OPPONENT} barSize={9}>
                <LabelList dataKey="opponent" position="right" formatter={label} fontSize={11} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <Caption data={serve} note={`Points won, summed over matches with stats; tournaments starting ${window.date_from} to ${window.date_to}.`} />
      </figure>
    </div>
  );
}

function label(value: unknown) {
  return typeof value === "number" ? `${value.toFixed(1)}%` : "";
}

function Caption<Row>({ data, note }: { data: ChartData<Row>; note: string }) {
  return (
    <figcaption>
      {note} Source: tool calls {data.sources.join(", ") || "none"}.
      {data.notes.length > 0 && (
        <ul className="chart-notes">{data.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
      )}
    </figcaption>
  );
}

const CELL_TEXT = { no_matches: "no matches", not_looked_up: "not looked up" } as const;

function cellText(cell: SurfaceRow["playerCell"]): string {
  if (cell.status !== "ok") return CELL_TEXT[cell.status];
  return cell.winRate === null ? `${cell.record}` : `${cell.record} (${cell.winRate.toFixed(1)}%)`;
}

type TipProps<Row> = { active?: boolean; payload?: { payload: Row }[]; player: PlayerRef; opponent: PlayerRef };

function SurfaceTip({ active, payload, player, opponent }: TipProps<SurfaceRow>) {
  const row = active && payload?.[0]?.payload;
  if (!row) return null;
  return (
    <div className="tooltip">
      <strong>{row.surface}</strong>
      <div>{player.name}: {cellText(row.playerCell)}</div>
      <div>{opponent.name}: {cellText(row.opponentCell)}</div>
    </div>
  );
}

function ServeTip({ active, payload, player, opponent }: TipProps<ServeRow>) {
  const row = active && payload?.[0]?.payload;
  if (!row) return null;
  return (
    <div className="tooltip">
      <strong>{row.metric}</strong>
      <div>{player.name}: {row.playerCounts ? `${row.player?.toFixed(1)}% (${row.playerCounts})` : "not available"}</div>
      <div>{opponent.name}: {row.opponentCounts ? `${row.opponent?.toFixed(1)}% (${row.opponentCounts})` : "not available"}</div>
    </div>
  );
}

function describeSurfaces(data: ChartData<SurfaceRow>, player: PlayerRef, opponent: PlayerRef): string {
  return "Win rate by surface. " + data.rows
    .map((r) => `${r.surface}: ${player.name} ${cellText(r.playerCell)}, ${opponent.name} ${cellText(r.opponentCell)}`)
    .join(". ");
}

function describeServe(data: ChartData<ServeRow>, player: PlayerRef, opponent: PlayerRef): string {
  const pct = (x: number | null) => (x === null ? "not available" : `${x.toFixed(1)}%`);
  return data.rows.map((r) => `${r.metric}: ${player.name} ${pct(r.player)}, ${opponent.name} ${pct(r.opponent)}`).join(". ");
}
