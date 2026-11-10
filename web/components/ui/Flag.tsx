// Small inline flags, by IOC code, drawn on one 24x16 grid so none of them letterboxes in a pin.
// A wrong flag is worse than none: a code that isn't here draws nothing. Flags whose bands match
// another country's (Croatia and the Netherlands, Slovakia, Slovenia and Russia) keep the shield
// that tells them apart.

import type { ReactNode } from "react";
import type { Locale } from "@/lib/i18n.ts";
import { useLanguage } from "./LanguageProvider.tsx";

const W = 24;
const H = 16;
const WHITE = "#F6F7F2";

function Bands({ colors, vertical = false }: { colors: string[]; vertical?: boolean }) {
  const size = (vertical ? W : H) / colors.length;
  return colors.map((fill, i) =>
    vertical
      ? <rect key={i} x={i * size} width={size} height={H} fill={fill} />
      : <rect key={i} y={i * size} width={W} height={size} fill={fill} />,
  );
}

function Stripes({ count, on, off, first = 0 }: { count: number; on: string; off: string; first?: number }) {
  const size = H / count;
  return (
    <>
      <rect width={W} height={H} fill={off} />
      {Array.from({ length: count }, (_, i) => i).filter((i) => i % 2 === first).map((i) => (
        <rect key={i} y={i * size} width={W} height={size} fill={on} />
      ))}
    </>
  );
}

function starPoints(cx: number, cy: number, r: number, points: number, rotate: number): string {
  const inner = points === 5 ? r * 0.382 : r * 0.45;
  return Array.from({ length: points * 2 }, (_, i) => {
    const angle = -Math.PI / 2 + rotate + (i * Math.PI) / points;
    const radius = i % 2 ? inner : r;
    return `${(cx + radius * Math.cos(angle)).toFixed(2)},${(cy + radius * Math.sin(angle)).toFixed(2)}`;
  }).join(" ");
}

function Star({ cx, cy, r, fill, points = 5, rotate = 0 }: { cx: number; cy: number; r: number; fill: string; points?: number; rotate?: number }) {
  return <polygon points={starPoints(cx, cy, r, points, rotate)} fill={fill} />;
}

function Cross({ x, y, width, color, thin }: { x: number; y: number; width: number; color: string; thin?: { x: number; y: number; width: number; color: string } }) {
  return (
    <>
      <rect x={x} width={width} height={H} fill={color} />
      <rect y={y} width={W} height={width} fill={color} />
      {thin && <Cross x={thin.x} y={thin.y} width={thin.width} color={thin.color} />}
    </>
  );
}

/** A heater shield with its top-left corner at (x, y). */
function shield(x: number, y: number, w: number, h: number): string {
  return `M${x} ${y}h${w}v${h * 0.58}q0 ${h * 0.3} ${-w / 2} ${h * 0.42}q${-w / 2} ${-h * 0.12} ${-w / 2} ${-h * 0.42}z`;
}

function UnionJack() {
  // The red diagonals sit to one side of the white ones, turning at the centre.
  const nx = 0.5547;
  const ny = 0.83205;
  const t = 1.1;
  return (
    <>
      <rect width={W} height={H} fill="#012169" />
      <path d="M-3-2L27 18M27-2L-3 18" stroke={WHITE} strokeWidth="3.2" />
      <g fill="#C8102E">
        <polygon points={`-3,-2 12,8 ${12 - nx * t},${8 + ny * t} ${-3 - nx * t},${-2 + ny * t}`} />
        <polygon points={`27,-2 12,8 ${12 - nx * t},${8 - ny * t} ${27 - nx * t},${-2 - ny * t}`} />
        <polygon points={`27,18 12,8 ${12 + nx * t},${8 - ny * t} ${27 + nx * t},${18 - ny * t}`} />
        <polygon points={`-3,18 12,8 ${12 + nx * t},${8 + ny * t} ${-3 + nx * t},${18 + ny * t}`} />
      </g>
      <path d="M12 0V16M0 8H24" stroke={WHITE} strokeWidth="5.4" />
      <path d="M12 0V16M0 8H24" stroke="#C8102E" strokeWidth="3.2" />
    </>
  );
}

function chinaStar(cx: number, cy: number) {
  const toBigStar = Math.atan2(4 - cy, 4 - cx) + Math.PI / 2;
  return <Star key={cx * 100 + cy} cx={cx} cy={cy} r={0.85} fill="#FFDE00" rotate={toBigStar} />;
}

const CANADA_LEAF = "12.23,13.04 12.11,10.88 12.39,10.63 14.54,11.01 14.25,10.21 14.3,10.03 16.65,8.12 16.12,7.88 16.04,7.68 16.5,6.25 15.15,6.54 14.96,6.44 14.7,5.82 13.64,6.96 13.37,6.82 13.88,4.19 13.06,4.66 12.83,4.59 12,2.96 11.17,4.59 10.94,4.66 10.13,4.19 10.64,6.82 10.36,6.96 9.3,5.82 9.04,6.44 8.86,6.54 7.5,6.25 7.97,7.68 7.88,7.88 7.35,8.12 9.7,10.03 9.75,10.21 9.46,11.01 11.61,10.63 11.89,10.88 11.78,13.04";

const FLAGS = new Map<string, { name: string; art: ReactNode }>([
  ["USA", {
    name: "United States",
    art: (
      <>
        <Stripes count={13} on="#B22234" off={WHITE} />
        <rect width="9.6" height={(H * 7) / 13} fill="#3C3B6E" />
        {[1.1, 2.7, 4.3, 5.9, 7.5].map((cy, row) =>
          [1.1, 3, 4.9, 6.8, 8.7].slice(0, row % 2 ? 4 : 5).map((cx) => (
            <circle key={`${cx}-${cy}`} cx={row % 2 ? cx + 0.95 : cx} cy={cy} r="0.42" fill={WHITE} />
          )),
        )}
      </>
    ),
  }],
  ["FRA", { name: "France", art: <Bands vertical colors={["#002395", WHITE, "#ED2939"]} /> }],
  ["ESP", {
    name: "Spain",
    art: (
      <>
        <rect width={W} height={H} fill="#C8313B" />
        <rect y="4" width={W} height="8" fill="#F2C335" />
      </>
    ),
  }],
  ["ITA", { name: "Italy", art: <Bands vertical colors={["#0B7A45", WHITE, "#C8313B"]} /> }],
  ["ARG", {
    name: "Argentina",
    art: (
      <>
        <Bands colors={["#74ACDF", WHITE, "#74ACDF"]} />
        <circle cx="12" cy="8" r="1.8" fill="#F6B40E" />
      </>
    ),
  }],
  ["AUS", {
    name: "Australia",
    art: (
      <>
        <rect width={W} height={H} fill="#00247D" />
        <svg width="12" height="8" viewBox={`0 0 ${W} ${H}`}>
          <UnionJack />
        </svg>
        <Star cx={6} cy={12} r={2.3} points={7} fill={WHITE} />
        <Star cx={18} cy={2.7} r={1.1} points={7} fill={WHITE} />
        <Star cx={15} cy={7} r={1.1} points={7} fill={WHITE} />
        <Star cx={20.9} cy={5.9} r={1.1} points={7} fill={WHITE} />
        <Star cx={19} cy={8.7} r={0.7} fill={WHITE} />
        <Star cx={18} cy={13.3} r={1.1} points={7} fill={WHITE} />
      </>
    ),
  }],
  ["GER", { name: "Germany", art: <Bands colors={["#000000", "#DD0000", "#FFCE00"]} /> }],
  ["RUS", { name: "Russia", art: <Bands colors={[WHITE, "#0039A6", "#D52B1E"]} /> }],
  ["SRB", {
    name: "Serbia",
    art: (
      <>
        <Bands colors={["#C6363C", "#0C4076", WHITE]} />
        <path d={shield(5.8, 3.8, 5.6, 8)} fill="#C6363C" stroke="#EDB92E" strokeWidth="0.6" />
        <rect x="8" y="5" width="1.2" height="5.6" fill={WHITE} />
        <rect x="6.8" y="6.8" width="3.6" height="1.2" fill={WHITE} />
      </>
    ),
  }],
  ["GBR", { name: "Great Britain", art: <UnionJack /> }],
  ["CAN", {
    name: "Canada",
    art: (
      <>
        <rect width={W} height={H} fill={WHITE} />
        <rect width="6" height={H} fill="#D80621" />
        <rect x="18" width="6" height={H} fill="#D80621" />
        <polygon points={CANADA_LEAF} fill="#D80621" />
      </>
    ),
  }],
  ["CZE", {
    name: "Czech Republic",
    art: (
      <>
        <Bands colors={[WHITE, "#D7141A"]} />
        <polygon points="0,0 12,8 0,16" fill="#11457E" />
      </>
    ),
  }],
  ["CRO", {
    name: "Croatia",
    art: (
      <>
        <Bands colors={["#D8262F", WHITE, "#171796"]} />
        <rect x="9" y="2.5" width="6" height="1.1" fill="#5B9BD5" />
        {[5, 5, 5, 5, 5, 3, 1].flatMap((count, row) =>
          Array.from({ length: count }, (_, col) => {
            const x = 12 - (count * 1.2) / 2 + col * 1.2;
            const fromCentre = col - (count - 1) / 2 + 2;
            return <rect key={`${row}-${col}`} x={x} y={3.6 + row * 1.2} width="1.2" height="1.2" fill={(row + fromCentre) % 2 === 0 ? "#D8262F" : WHITE} />;
          }),
        )}
      </>
    ),
  }],
  ["JPN", {
    name: "Japan",
    art: (
      <>
        <rect width={W} height={H} fill={WHITE} />
        <circle cx="12" cy="8" r="4.8" fill="#BC002D" />
      </>
    ),
  }],
  ["SUI", {
    name: "Switzerland",
    art: (
      <>
        <rect width={W} height={H} fill="#D52B1E" />
        <rect x="7" y="6.5" width="10" height="3" fill={WHITE} />
        <rect x="10.5" y="3" width="3" height="10" fill={WHITE} />
      </>
    ),
  }],
  ["BEL", { name: "Belgium", art: <Bands vertical colors={["#000000", "#FAE042", "#ED2939"]} /> }],
  ["NED", { name: "Netherlands", art: <Bands colors={["#AE1C28", WHITE, "#21468B"]} /> }],
  ["AUT", { name: "Austria", art: <Bands colors={["#ED2939", WHITE, "#ED2939"]} /> }],
  ["KAZ", {
    name: "Kazakhstan",
    art: (
      <>
        <rect width={W} height={H} fill="#00AFCA" />
        {[1.6, 3.8, 6, 8.2, 10.4, 12.6, 14.8].map((y) => (
          <polygon key={y} points={`1.8,${y - 0.9} 2.6,${y} 1.8,${y + 0.9} 1,${y}`} fill="#FEC50C" />
        ))}
        <circle cx="13" cy="6.4" r="2.5" fill="#FEC50C" />
        <circle cx="13" cy="6.4" r="3.8" fill="none" stroke="#FEC50C" strokeWidth="0.9" strokeDasharray="0.75 0.75" />
        <path d="M7.6 9.2C10 11.4 11.6 11.2 13 12.8 14.4 11.2 16 11.4 18.4 9.2 16 10 14.4 10 13 10.8 11.6 10 10 10 7.6 9.2Z" fill="#FEC50C" />
      </>
    ),
  }],
  ["POR", {
    name: "Portugal",
    art: (
      <>
        <rect width="9.6" height={H} fill="#046A38" />
        <rect x="9.6" width="14.4" height={H} fill="#DA291C" />
        <circle cx="9.6" cy="8" r="3.8" fill="#FFE000" />
        <path d={shield(7.7, 5.2, 3.8, 5.2)} fill="#DA291C" />
        <path d={shield(8.6, 6.1, 2, 3)} fill={WHITE} />
      </>
    ),
  }],
  ["CHI", {
    name: "Chile",
    art: (
      <>
        <Bands colors={[WHITE, "#D52B1E"]} />
        <rect width="8" height="8" fill="#0039A6" />
        <Star cx={4} cy={4} r={2.7} fill={WHITE} />
      </>
    ),
  }],
  ["BRA", {
    name: "Brazil",
    art: (
      <>
        <rect width={W} height={H} fill="#009C3B" />
        <polygon points="2,8 12,1.9 22,8 12,14.1" fill="#FFDF00" />
        <circle cx="12" cy="8" r="4" fill="#002776" />
        <path d="M8.2 6.9C11 6.5 13.8 7.2 15.8 9.2" fill="none" stroke={WHITE} strokeWidth="0.75" />
      </>
    ),
  }],
  ["POL", { name: "Poland", art: <Bands colors={[WHITE, "#DC143C"]} /> }],
  ["BUL", { name: "Bulgaria", art: <Bands colors={[WHITE, "#00966E", "#D62612"]} /> }],
  ["GRE", {
    name: "Greece",
    art: (
      <>
        <Stripes count={9} on="#0D5EAF" off={WHITE} />
        <rect width={(H * 5) / 9} height={(H * 5) / 9} fill="#0D5EAF" />
        <rect x={(H * 2) / 9} width={H / 9} height={(H * 5) / 9} fill={WHITE} />
        <rect y={(H * 2) / 9} width={(H * 5) / 9} height={H / 9} fill={WHITE} />
      </>
    ),
  }],
  ["SVK", {
    name: "Slovakia",
    art: (
      <>
        <Bands colors={[WHITE, "#0B4EA2", "#EE1C25"]} />
        <path d={shield(3.6, 2.8, 8.8, 10.4)} fill={WHITE} />
        <path d={shield(4.3, 3.5, 7.4, 9)} fill="#EE1C25" />
        <rect x="7.4" y="4.4" width="1.2" height="6" fill={WHITE} />
        <rect x="6.1" y="5.4" width="3.8" height="1" fill={WHITE} />
        <rect x="5.4" y="7.2" width="5.2" height="1" fill={WHITE} />
        <path d="M5 10.3Q6.6 8.9 8 10.1 9.4 8.9 11 10.3 9.8 11.9 8 12.5 6.2 11.9 5 10.3Z" fill="#0B4EA2" />
      </>
    ),
  }],
  ["HUN", { name: "Hungary", art: <Bands colors={["#CE2939", WHITE, "#477050"]} /> }],
  ["NOR", {
    name: "Norway",
    art: (
      <>
        <rect width={W} height={H} fill="#BA0C2F" />
        <Cross x={6.5} y={6} width={4} color={WHITE} thin={{ x: 7.5, y: 7, width: 2, color: "#00205B" }} />
      </>
    ),
  }],
  ["RSA", {
    name: "South Africa",
    art: (
      <>
        <rect width={W} height="8" fill="#E03C31" />
        <rect y="8" width={W} height="8" fill="#001489" />
        <path d="M-6-4L12 8H30M-6 20L12 8" fill="none" stroke={WHITE} strokeWidth="5.33" />
        <polygon points="0,0 12,8 0,16" fill="#FFB81C" />
        <polygon points="0,3.2 7.19,8 0,12.8" fill="#000000" />
        <path d="M-6-4L12 8H30M-6 20L12 8" fill="none" stroke="#007749" strokeWidth="3.2" />
      </>
    ),
  }],
  ["CHN", {
    name: "China",
    art: (
      <>
        <rect width={W} height={H} fill="#DE2910" />
        <Star cx={4} cy={4} r={2.4} fill="#FFDE00" />
        {chinaStar(8, 1.6)}
        {chinaStar(9.6, 3.2)}
        {chinaStar(9.6, 5.6)}
        {chinaStar(8, 7.2)}
      </>
    ),
  }],
  ["BIH", {
    name: "Bosnia and Herzegovina",
    art: (
      <>
        <rect width={W} height={H} fill="#002395" />
        <polygon points="6.36,0 18.36,0 18.36,16" fill="#FECB00" />
        {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((k) => (
          <Star key={k} cx={2.03 + 1.5 * k} cy={2 * k} r={0.9} fill={WHITE} />
        ))}
      </>
    ),
  }],
  ["GEO", {
    name: "Georgia",
    art: (
      <>
        <rect width={W} height={H} fill={WHITE} />
        <Cross x={10.4} y={6.4} width={3.2} color="#E01F2D" />
        {[[5.2, 3.2], [18.8, 3.2], [5.2, 12.8], [18.8, 12.8]].map(([cx, cy]) => (
          <path key={`${cx}-${cy}`} d={`M${cx - 2} ${cy}H${cx + 2}M${cx} ${cy - 2}V${cy + 2}`} stroke="#E01F2D" strokeWidth="1.1" />
        ))}
      </>
    ),
  }],
  ["UKR", { name: "Ukraine", art: <Bands colors={["#0057B7", "#FFD700"]} /> }],
  ["DEN", {
    name: "Denmark",
    art: (
      <>
        <rect width={W} height={H} fill="#C8102E" />
        <Cross x={7.7} y={6.85} width={2.3} color={WHITE} />
      </>
    ),
  }],
  ["SLO", {
    name: "Slovenia",
    art: (
      <>
        <Bands colors={[WHITE, "#005DA4", "#ED1C24"]} />
        <path d={shield(4.6, 2.4, 4.8, 6)} fill="#005DA4" stroke="#ED1C24" strokeWidth="0.5" />
        <polygon points="5.5,6.7 7,3.9 8.5,6.7" fill={WHITE} />
        <circle cx="5.9" cy="3.3" r="0.32" fill="#FFE000" />
        <circle cx="8.1" cy="3.3" r="0.32" fill="#FFE000" />
        <circle cx="7" cy="3.3" r="0.32" fill="#FFE000" />
      </>
    ),
  }],
  ["KOR", {
    name: "South Korea",
    art: (
      <>
        <rect width={W} height={H} fill={WHITE} />
        <g transform="translate(12 8) scale(0.33333)">
          <g transform="rotate(-56.3099)">
            <path d="M-6-25H6M-6-22H6M-6-19H6M-6 19H6M-6 22H6M-6 25H6" stroke="#000000" strokeWidth="2" />
            <path d="M0 17V27" stroke={WHITE} strokeWidth="1" />
            <circle r="12" fill="#CD2E3A" />
            <path d="M0-12A6 6 0 0 0 0 0A6 6 0 0 1 0 12A12 12 0 0 1 0-12Z" fill="#0047A0" />
          </g>
          <g transform="rotate(-123.69)">
            <path d="M-6-25H6M-6-22H6M-6-19H6M-6 19H6M-6 22H6M-6 25H6" stroke="#000000" strokeWidth="2" />
            <path d="M0-23.5V-20.5M0 17V20.5M0 23.5V26.5" stroke={WHITE} strokeWidth="1" />
          </g>
        </g>
      </>
    ),
  }],
  ["SWE", {
    name: "Sweden",
    art: (
      <>
        <rect width={W} height={H} fill="#006AA7" />
        <Cross x={7.5} y={6.4} width={3.2} color="#FECC00" />
      </>
    ),
  }],
  ["FIN", {
    name: "Finland",
    art: (
      <>
        <rect width={W} height={H} fill={WHITE} />
        <Cross x={6.67} y={5.82} width={4.36} color="#002F6C" />
      </>
    ),
  }],
  ["COL", {
    name: "Colombia",
    art: (
      <>
        <rect width={W} height="8" fill="#FCD116" />
        <rect y="8" width={W} height="4" fill="#003893" />
        <rect y="12" width={W} height="4" fill="#CE1126" />
      </>
    ),
  }],
  ["URU", {
    name: "Uruguay",
    art: (
      <>
        <Stripes count={9} on="#0038A8" off={WHITE} first={1} />
        <rect width={(H * 5) / 9} height={(H * 5) / 9} fill={WHITE} />
        <circle cx={(H * 5) / 18} cy={(H * 5) / 18} r="3.1" fill="none" stroke="#FCD116" strokeWidth="1.2" strokeDasharray="0.61 0.61" />
        <circle cx={(H * 5) / 18} cy={(H * 5) / 18} r="2" fill="#FCD116" />
      </>
    ),
  }],
  ["PHI", {
    name: "Philippines",
    art: (
      <>
        <rect width={W} height="8" fill="#1A3E8C" />
        <rect y="8" width={W} height="8" fill="#C8313B" />
        <polygon points="0,0 13.86,8 0,16" fill={WHITE} />
        <circle cx="4.5" cy="8" r="1.6" fill="#F2C335" />
      </>
    ),
  }],
]);

export function hasFlag(code: string | null | undefined): boolean {
  return code != null && FLAGS.has(code);
}

// For naming a country in Spanish or French with the browser's own names (Intl.DisplayNames).
const ISO_REGION: Record<string, string> = {
  USA: "US", FRA: "FR", ESP: "ES", ITA: "IT", ARG: "AR", AUS: "AU", GER: "DE", RUS: "RU", SRB: "RS", GBR: "GB", CAN: "CA",
  CZE: "CZ", CRO: "HR", JPN: "JP", SUI: "CH", BEL: "BE", NED: "NL", AUT: "AT", KAZ: "KZ", POR: "PT", CHI: "CL", BRA: "BR",
  POL: "PL", BUL: "BG", GRE: "GR", SVK: "SK", HUN: "HU", NOR: "NO", RSA: "ZA", CHN: "CN", BIH: "BA", GEO: "GE", UKR: "UA",
  DEN: "DK", SLO: "SI", KOR: "KR", SWE: "SE", FIN: "FI", COL: "CO", URU: "UY", PHI: "PH",
};

/** The country's name for a code with a flag, in the given language; null for any other code. */
export function countryName(code: string | null | undefined, locale: Locale = "en"): string | null {
  const name = (code != null && FLAGS.get(code)?.name) || null;
  if (!name || locale === "en" || code == null || !Object.hasOwn(ISO_REGION, code)) return name;
  try {
    return new Intl.DisplayNames([locale], { type: "region" }).of(ISO_REGION[code]) ?? name;
  } catch {
    return name;
  }
}

export type FlagProps = {
  country: string | null | undefined;
  width?: number;
  height?: number;
  className?: string;
};

/** Draws the flag for an IOC code, or nothing when the code has no flag here. */
export function Flag({ country, width = W, height = H, className }: FlagProps) {
  const { locale } = useLanguage();
  const flag = country == null ? undefined : FLAGS.get(country);
  if (!flag) return null;
  return (
    <svg className={className} width={width} height={height} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice" role="img" aria-label={countryName(country, locale) ?? flag.name}>
      {flag.art}
      <rect className="flag-sheen" width={W} height="2.2" fill="#FFFFFF" opacity="0" />
    </svg>
  );
}
