// Names, dates and the data's codes as they read on screen.

import assert from "node:assert/strict";
import { test } from "node:test";
import { eventName, handName, initials, lastName, longDate, monthYear, roundName } from "./people.ts";

test("initials use the first and last words", () => {
  assert.equal(initials("Jannik Sinner"), "JS");
  assert.equal(initials("Francis Casey Alcantara"), "FA");
  assert.equal(initials("Juan Martin del Potro"), "JP");
  assert.equal(initials("  Carlos   Alcaraz "), "CA");
  assert.equal(initials("Hod'abalo isak Padio"), "HP");
  assert.equal(initials("Federer"), "F");
  assert.equal(initials(""), "");
});

test("the last name keeps particles and known two-word surnames, and nothing else", () => {
  assert.equal(lastName("Carlos Alcaraz"), "Alcaraz");
  assert.equal(lastName("Francis Casey Alcantara"), "Alcantara");
  assert.equal(lastName("Juan Pablo Varillas"), "Varillas");
  assert.equal(lastName("Alex De Minaur"), "De Minaur");
  assert.equal(lastName("Juan Martin del Potro"), "del Potro");
  assert.equal(lastName("Botic Van De Zandschulp"), "Van De Zandschulp");
  assert.equal(lastName("Roberto Bautista Agut"), "Bautista Agut");
  assert.equal(lastName("Felix Auger Aliassime"), "Auger Aliassime");
  assert.equal(lastName("Edouard Roger-Vasselin"), "Roger-Vasselin");
  assert.equal(lastName("Federer"), "Federer");
  assert.equal(lastName(""), "");
});

test("a particle at the start of a name is a first name", () => {
  assert.equal(lastName("Van Nguyen"), "Nguyen");
});

for (const zone of ["UTC", "Pacific/Honolulu", "Asia/Tokyo", "Pacific/Kiritimati"]) {
  test(`dates don't move in ${zone}`, (t) => {
    const saved = process.env.TZ;
    process.env.TZ = zone;
    t.after(() => {
      if (saved === undefined) delete process.env.TZ;
      else process.env.TZ = saved;
    });
    assert.equal(longDate("2020-02-17"), "17 February 2020");
    assert.equal(monthYear("2026-10-26"), "Oct 2026");
    assert.equal(longDate("2020-02-17T23:59:59Z"), "17 February 2020", "just before midnight UTC");
    assert.equal(longDate("2020-02-18T00:00:00Z"), "18 February 2020", "exactly midnight UTC");
    assert.equal(longDate("2020-02-17T23:59:59"), "17 February 2020", "a time with no offset is UTC");
    assert.equal(longDate("2020-02-17T23:30:00-05:00"), "18 February 2020", "an offset is converted to UTC");
    assert.equal(monthYear("2026-12-31T23:59:59Z"), "Dec 2026");
    assert.equal(monthYear("2026-01-01T00:00:00Z"), "Jan 2026");
    assert.equal(monthYear("2026-09-30"), "Sep 2026");
  });
}

test("text that isn't an ISO date comes back unchanged, never as Invalid Date", () => {
  assert.equal(longDate("not a date"), "not a date");
  assert.equal(longDate("2020-13-45"), "2020-13-45");
  assert.equal(monthYear(""), "");
});

test("tournament names are cleaned for display", () => {
  assert.equal(eventName("Us Open"), "US Open");
  assert.equal(eventName("US Open"), "US Open");
  assert.equal(eventName("s Hertogenbosch"), "'s-Hertogenbosch");
  assert.equal(eventName("'s-Hertogenbosch"), "'s-Hertogenbosch");
  assert.equal(eventName("Davis Cup Finals QF: ITA vs ARG"), "Davis Cup Finals");
  assert.equal(eventName("Davis Cup G1 R1: AUT vs BLR"), "Davis Cup");
  assert.equal(eventName("Davis Cup WG PO: FRA vs SRB"), "Davis Cup");
  assert.equal(eventName("Atp Cup"), "ATP Cup");
  assert.equal(eventName("Rio De Janeiro"), "Rio de Janeiro");
  assert.equal(eventName("ATP Rio de Janeiro"), "Rio de Janeiro");
  assert.equal(eventName("NextGen Finals"), "Next Gen Finals");
  assert.equal(eventName("St Petersburg"), "St. Petersburg");
  assert.equal(eventName("Belgrade "), "Belgrade");
  assert.equal(eventName("Cologne 2"), "Cologne 2");
  assert.equal(eventName("Queen's Club"), "Queen's Club");
});

test("round codes read as words, and unknown codes are left alone", () => {
  const expected = {
    F: "Final", SF: "Semifinal", QF: "Quarterfinal", R16: "Round of 16", R32: "Round of 32",
    R64: "Round of 64", R128: "Round of 128", RR: "Round robin", BR: "Bronze medal match",
  };
  for (const [code, name] of Object.entries(expected)) assert.equal(roundName(code), name);
  assert.equal(roundName("Q1"), "Q1");
  assert.equal(roundName("constructor"), "constructor");
});

test("the hand is named only when it is known", () => {
  assert.equal(handName("R"), "right-handed");
  assert.equal(handName("L"), "left-handed");
  assert.equal(handName("U"), null);
  assert.equal(handName(null), null);
  assert.equal(handName(undefined), null);
});
