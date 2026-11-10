import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import { EN, LOCALES, MESSAGES, localeCookie, pickLocale } from "./i18n.ts";
import { findFigure } from "./plan.ts";
import { longDate, monthYear, roundName } from "./people.ts";
import { showingText } from "./player-stats.ts";

const { es, fr } = MESSAGES;

// ---------- picking the language (D-027) ----------

test("a saved choice wins, and only one of the app's languages counts as saved", () => {
  assert.equal(pickLocale("fr", "es-ES,es;q=0.9"), "fr");
  assert.equal(pickLocale("de", "es"), "es");
  assert.equal(pickLocale("", "fr"), "fr");
});

test("the browser's languages are matched on the base language, by preference", () => {
  assert.equal(pickLocale(undefined, "es-419"), "es");
  assert.equal(pickLocale(undefined, "fr-CA,en;q=0.8"), "fr");
  assert.equal(pickLocale(undefined, "de, fr;q=0.8, en;q=0.5"), "fr");
  assert.equal(pickLocale(undefined, "en;q=0.4, es;q=0.9"), "es");
  assert.equal(pickLocale(undefined, "en-US,en;q=0.9,es;q=0.8"), "en");
});

test("a language the browser rules out, or a broken weight, is skipped", () => {
  assert.equal(pickLocale(undefined, "es;q=0, fr"), "fr");
  assert.equal(pickLocale(undefined, "es;q=abc, fr;q=0.5"), "fr");
});

test("with nothing usable the app is in English", () => {
  for (const header of [null, undefined, "", "*", "de, it;q=0.8", " ; q=1"]) assert.equal(pickLocale(null, header), "en");
});

test("the cookie holds only the code, for a year, and is Secure over https", () => {
  assert.equal(localeCookie("es", true), "lang=es; Path=/; Max-Age=31536000; SameSite=Lax; Secure");
  assert.equal(localeCookie("fr", false), "lang=fr; Path=/; Max-Age=31536000; SameSite=Lax");
});

// ---------- every language says everything ----------

test("every language has every string and list English has, with the same arguments", () => {
  const ownKeys = (x: object) => Object.keys(x).sort();
  for (const locale of LOCALES) {
    const t = MESSAGES[locale] as Record<string, unknown>;
    assert.deepEqual(ownKeys(t), ownKeys(EN), locale);
    for (const [key, english] of Object.entries(EN)) {
      const value = t[key];
      if (typeof english === "function") assert.equal((value as (...a: unknown[]) => unknown).length, english.length, `${locale}.${key}`);
      else if (typeof english === "string") assert.ok(typeof value === "string" && value.trim(), `${locale}.${key}`);
      else if (Array.isArray(english)) assert.equal((value as unknown[]).length, english.length, `${locale}.${key}`);
      else if (key !== "errors" && key !== "serverMessages") assert.deepEqual(ownKeys(value as object), ownKeys(english as object), `${locale}.${key}`);
    }
  }
  // English shows the API's own messages; the others translate the same ones.
  assert.deepEqual(Object.keys(es.errors).sort(), Object.keys(fr.errors).sort());
  assert.deepEqual(Object.keys(es.serverMessages).sort(), Object.keys(fr.serverMessages).sort());
});

// ---------- numbers and dates ----------

test("Spanish and French change the decimal mark and the percent sign, never the digits", () => {
  assert.equal(EN.pct("75.7"), "75.7%");
  assert.equal(es.pct("75.7"), "75,7 %");
  assert.equal(fr.pct("0.0"), "0,0 %");
  assert.equal(es.dec("4.5"), "4,5");
  assert.equal(EN.int(12345), "12,345");
  assert.equal(es.int(12345), "12.345");
  assert.equal(fr.int(12345), "12 345");
});

test("dates read in each language, in UTC", () => {
  assert.equal(longDate("2026-11-01", EN), "1 November 2026");
  assert.equal(longDate("2026-11-01", es), "1 de noviembre de 2026");
  assert.equal(longDate("2026-11-01", fr), "1er novembre 2026");
  assert.equal(longDate("2024-10-26T23:30:00", fr), "26 octobre 2024");
  assert.equal(monthYear("2026-10-26", es), "oct 2026");
  assert.equal(monthYear("2026-02-02", fr), "févr. 2026");
  assert.equal(longDate("soon", es), "soon");
});

test("round names are translated, and an unknown code is shown as it is", () => {
  assert.equal(roundName("QF", es), "Cuartos de final");
  assert.equal(roundName("R16", fr), "8e de finale");
  assert.equal(roundName("toString", es), "toString");
});

test("a Spanish page's filters read in Spanish", () => {
  assert.equal(showingText({ surface: "Clay", season: 2025 }, es), "Mostrando pistas de tierra batida, 2025.");
  assert.equal(showingText({ surface: null, season: null }, fr), "Affichage : toutes les surfaces, toutes les saisons.");
});

// ---------- figures in the model's text ----------

const CHECKED = [
  { value: "56.5", side: "opponent" as const, against: "60.4", sample: 29 },
  { value: "60.4", side: "player" as const, against: "56.5", sample: 32 },
];
const NAMES = { player: "Sinner", opponent: "Alcaraz" };

test("a figure written with a decimal comma is found when the evidence has it", () => {
  const figure = findFigure("Ataca el segundo saque. Alcaraz ganó el 56,5 % de esos puntos, frente al 60,4 % de Sinner.", CHECKED, NAMES, es);
  assert.deepEqual(figure, { text: "56,5 %", sub: "Alcaraz, frente al 60,4 % de Sinner", sample: 29, small: false });
  const french = findFigure("Attaquez la deuxième balle : 56,5 % contre 60,4 %.", CHECKED, NAMES, fr);
  assert.equal(french?.text, "56,5 %");
});

test("a comma figure the evidence doesn't have still puts nothing on screen", () => {
  assert.equal(findFigure("Gana el 56,4 % de esos puntos.", CHECKED, NAMES, es), null);
  assert.equal(findFigure("Gana el 56,50 % de esos puntos.", CHECKED, NAMES, es), null);
});

// ---------- guard: words on screen go through the messages ----------

const ALLOWED = new Set(["Tennis Scouting Analyst", "Tennis Abstract", "CC BY-NC-SA 4.0"]);

test("components show no words of their own, only names and messages", () => {
  const found: string[] = [];
  for (const dir of ["../components", "../app"]) {
    const root = new URL(dir, import.meta.url);
    for (const name of readdirSync(root, { recursive: true }) as string[]) {
      if (!name.endsWith(".tsx")) continue;
      const source = readFileSync(new URL(`${dir}/${name}`, import.meta.url), "utf8");
      for (const m of source.matchAll(/>\s*([^<>{}\n]*\p{L}{2,}[^<>{}\n]*?)\s*</gu)) {
        if (!ALLOWED.has(m[1].trim())) found.push(`${name}: ${m[1].trim()}`);
      }
      for (const m of source.matchAll(/\b(?:placeholder|aria-label|title|label|help|changeLabel|alt)="([^"]*\p{L}{2,}[^"]*)"/gu)) {
        if (!ALLOWED.has(m[1])) found.push(`${name}: ${m[1]}`);
      }
    }
  }
  assert.deepEqual(found, []);
});
