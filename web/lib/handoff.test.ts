// Moving chosen players to match setup through sessionStorage, with a stand-in store.

import assert from "node:assert/strict";
import { type TestContext, test } from "node:test";
import { saveHandoff, takeHandoff } from "./handoff.ts";
import type { Candidate } from "./types.ts";

const KEY = "clubhouse-handoff";

const alcaraz: Candidate = {
  player_id: 207989, name: "Carlos Alcaraz", country: "ESP", hand: "R", matches_loaded: 389, last_tourney_date: "2026-10-26",
};
const sinner: Candidate = {
  player_id: 206173, name: "Jannik Sinner", country: "ITA", hand: null, matches_loaded: 464, last_tourney_date: null,
};

class FakeStorage {
  data = new Map<string, string>();
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
}

/** Puts `descriptor` at globalThis.sessionStorage for one test. */
function installStore(t: TestContext, descriptor: PropertyDescriptor) {
  const saved = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, ...descriptor });
  t.after(() => {
    if (saved) Object.defineProperty(globalThis, "sessionStorage", saved);
    else delete (globalThis as { sessionStorage?: unknown }).sessionStorage;
  });
}

function fakeStore(t: TestContext) {
  const store = new FakeStorage();
  installStore(t, { value: store });
  return store;
}

test("a saved handoff comes back once, and is then gone", (t) => {
  const store = fakeStore(t);
  saveHandoff({ player: sinner, opponent: alcaraz });
  assert.deepEqual(takeHandoff(), { player: sinner, opponent: alcaraz });
  assert.equal(store.data.size, 0);
  assert.equal(takeHandoff(), null);
});

test("either player can be handed over alone", (t) => {
  fakeStore(t);
  saveHandoff({ opponent: alcaraz });
  assert.deepEqual(takeHandoff(), { opponent: alcaraz });
  saveHandoff({ player: sinner });
  assert.deepEqual(takeHandoff(), { player: sinner });
});

test("an empty store is no handoff", (t) => {
  fakeStore(t);
  assert.equal(takeHandoff(), null);
});

test("a handoff with no players is no handoff", (t) => {
  fakeStore(t);
  saveHandoff({});
  assert.equal(takeHandoff(), null);
});

test("no store at all, as on the server, is no handoff", (t) => {
  installStore(t, { value: undefined });
  assert.doesNotThrow(() => saveHandoff({ player: sinner }));
  assert.equal(takeHandoff(), null);
});

test("a store whose methods throw is no handoff", (t) => {
  const refuse = () => {
    throw new DOMException("denied", "SecurityError");
  };
  installStore(t, { value: { getItem: refuse, setItem: refuse, removeItem: refuse } });
  assert.doesNotThrow(() => saveHandoff({ player: sinner }));
  assert.equal(takeHandoff(), null);
});

test("a store that can't even be opened is no handoff", (t) => {
  installStore(t, {
    get() {
      throw new DOMException("denied", "SecurityError");
    },
  });
  assert.doesNotThrow(() => saveHandoff({ player: sinner }));
  assert.equal(takeHandoff(), null);
});

test("a store that can read but not clear is no handoff, so it can't apply twice", (t) => {
  const store = fakeStore(t);
  store.setItem(KEY, JSON.stringify({ player: sinner }));
  store.removeItem = () => {
    throw new DOMException("denied", "SecurityError");
  };
  assert.equal(takeHandoff(), null);
});

test("corrupt JSON is no handoff, and is cleared", (t) => {
  const store = fakeStore(t);
  store.setItem(KEY, "{not json");
  assert.equal(takeHandoff(), null);
  assert.equal(store.data.size, 0);
});

const badShapes: [string, unknown][] = [
  ["null", null],
  ["an array", [sinner]],
  ["a number", 7],
  ["a player that isn't an object", { player: "Sinner" }],
  ["a null player", { player: null }],
  ["a good player beside a bad opponent", { player: sinner, opponent: { name: "Nobody" } }],
  ["a string player_id", { player: { ...sinner, player_id: "206173" } }],
  ["a fractional player_id", { player: { ...sinner, player_id: 1.5 } }],
  ["a player_id of zero", { player: { ...sinner, player_id: 0 } }],
  ["no name", { player: { ...sinner, name: undefined } }],
  ["a blank name", { player: { ...sinner, name: "  " } }],
  ["a number for a country", { player: { ...sinner, country: 39 } }],
  ["a number for a hand", { player: { ...sinner, hand: 1 } }],
  ["matches as text", { player: { ...sinner, matches_loaded: "464" } }],
  ["negative matches", { player: { ...sinner, matches_loaded: -1 } }],
  ["no matches field", { player: { ...sinner, matches_loaded: undefined } }],
  ["a number for a date", { player: { ...sinner, last_tourney_date: 20260629 } }],
];

for (const [label, value] of badShapes) {
  test(`${label} is no handoff, and is cleared`, (t) => {
    const store = fakeStore(t);
    store.setItem(KEY, JSON.stringify(value));
    assert.equal(takeHandoff(), null);
    assert.equal(store.data.size, 0);
  });
}

test("the same player on both sides is no handoff", (t) => {
  fakeStore(t);
  saveHandoff({ player: sinner, opponent: sinner });
  assert.equal(takeHandoff(), null);
});

test("only the known fields are passed on", (t) => {
  const store = fakeStore(t);
  store.setItem(KEY, JSON.stringify({ player: { ...sinner, birth_date: "2020-02-02" }, extra: true }));
  assert.deepEqual(takeHandoff(), { player: sinner });
});
