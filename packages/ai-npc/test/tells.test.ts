import { describe, it, expect } from "vitest";
import { PERSONALITY_TELLS, pickTell } from "../src/tells.js";
import type { TellTrigger } from "../src/tells.js";
import type { NpcPersonality } from "@blackjack/engine";

const ALL_IDS: NpcPersonality[] = [
  "optimal",
  "counter",
  "amateur",
  "chaser",
  "superstitious",
  "ritualistic",
  "risk_averse",
];

describe("PERSONALITY_TELLS", () => {
  it("has all 7 keys", () => {
    expect(Object.keys(PERSONALITY_TELLS).sort()).toEqual([...ALL_IDS].sort());
  });

  it("optimal has an empty tells array (poker-faced)", () => {
    expect(PERSONALITY_TELLS.optimal).toEqual([]);
  });

  it("every tell has a valid trigger, gesture, and strength in [0,1]", () => {
    const validTriggers: TellTrigger[] = [
      "before-hit",
      "before-stand",
      "before-double",
      "before-split",
      "on-bust",
      "on-win",
      "on-loss",
      "on-strong-hand",
      "on-weak-hand",
    ];
    const validGestures = [
      "confident",
      "nervous",
      "poker-face",
      "taunt",
      "sigh",
      "celebrate",
    ];
    for (const id of ALL_IDS) {
      for (const tell of PERSONALITY_TELLS[id]) {
        expect(validTriggers).toContain(tell.trigger);
        expect(validGestures).toContain(tell.gesture);
        expect(tell.strength).toBeGreaterThanOrEqual(0);
        expect(tell.strength).toBeLessThanOrEqual(1);
      }
    }
  });

  it("each personality has 0-3 tells", () => {
    for (const id of ALL_IDS) {
      expect(PERSONALITY_TELLS[id].length).toBeLessThanOrEqual(3);
    }
  });
});

describe("pickTell", () => {
  it("returns null when no tell matches the trigger", () => {
    // optimal has no tells at all → always null.
    expect(pickTell("optimal", "before-hit", 1)).toBe(null);
    // ritualistic has no 'on-win' tell → null.
    expect(pickTell("ritualistic", "on-win", 1)).toBe(null);
  });

  it("is deterministic: same (personality, trigger, seed) → same result", () => {
    for (let seed = 0; seed < 20; seed++) {
      const a = pickTell("amateur", "on-strong-hand", seed);
      const b = pickTell("amateur", "on-strong-hand", seed);
      expect(a).toBe(b);
    }
  });

  it("returns the gesture when strength is effectively 1.0", () => {
    // ritualistic.before-split has strength 0.9 — try several seeds and
    // confirm the gesture surfaces for at least one; and for strength 1.0
    // synthesize via manipulating PERSONALITY_TELLS is invasive. Instead:
    // test that a known high-strength tell fires for some deterministic seed.
    const seenGesture: string[] = [];
    for (let seed = 0; seed < 50; seed++) {
      const g = pickTell("ritualistic", "before-split", seed);
      if (g !== null) seenGesture.push(g);
    }
    // Strength 0.9 over 50 trials → overwhelmingly likely to fire at least once.
    expect(seenGesture.length).toBeGreaterThan(0);
    expect(seenGesture.every((g) => g === "poker-face")).toBe(true);
  });

  it("never returns a gesture for strength 0 (synthetic via empty bank)", () => {
    // No tell for this trigger at all on counter → always null.
    for (let seed = 0; seed < 20; seed++) {
      expect(pickTell("counter", "before-stand", seed)).toBe(null);
    }
  });

  it("produces a mix of hits and misses for strengths in (0,1)", () => {
    const results: (string | null)[] = [];
    for (let seed = 0; seed < 100; seed++) {
      results.push(pickTell("amateur", "before-stand", seed));
    }
    const hits = results.filter((r) => r !== null).length;
    const misses = results.filter((r) => r === null).length;
    // Strength is 0.4 — over 100 trials we expect a real mix.
    expect(hits).toBeGreaterThan(0);
    expect(misses).toBeGreaterThan(0);
  });
});
