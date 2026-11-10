// Number formats per language. Figures arrive already rounded as text ("75.7"), so a language
// only changes the decimal mark and the percent sign, never the digits.

export type Locale = "en" | "es" | "fr";

/** How a surface reads in a sentence. `name` is the label on a tile or card. */
export interface SurfaceWords {
  name: string; // "Clay"
  lower: string; // "clay"
  on: string; // "on clay"
  onCap: string; // "On clay"
  courts: string; // "clay courts"
  courtsCap: string; // "Clay courts"
}

const NBSP = " ";
const comma = (text: string) => text.replace(".", ",");

export const enFormat = {
  int: (n: number) => n.toLocaleString("en-US"),
  dec: (text: string) => text,
  pct: (text: string) => `${text}%`,
};

export const esFormat = {
  int: (n: number) => n.toLocaleString("es-ES"),
  dec: comma,
  pct: (text: string) => `${comma(text)}${NBSP}%`,
};

export const frFormat = {
  int: (n: number) => n.toLocaleString("fr-FR"),
  dec: comma,
  pct: (text: string) => `${comma(text)}${NBSP}%`,
};

export const lowerFirst = (text: string) => `${text.charAt(0).toLowerCase()}${text.slice(1)}`;
