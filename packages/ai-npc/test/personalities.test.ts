import { describe, it, expect } from "vitest";
import { PERSONALITIES } from "../src/personalities.js";
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

describe("PERSONALITIES", () => {
  it("has all 7 keys", () => {
    expect(Object.keys(PERSONALITIES).sort()).toEqual([...ALL_IDS].sort());
  });

  it("each config has the required fields", () => {
    for (const id of ALL_IDS) {
      const cfg = PERSONALITIES[id];
      expect(cfg.id).toBe(id);
      expect(typeof cfg.nameZh).toBe("string");
      expect(typeof cfg.nameEn).toBe("string");
      expect(typeof cfg.description).toBe("string");
      expect(["flat", "kelly", "reverse-martingale", "unit-spread"]).toContain(
        cfg.betPolicy,
      );
      expect(cfg.betUnitMultiplier).toBeGreaterThan(0);
      expect(cfg.playNoise).toBeGreaterThanOrEqual(0);
      expect(cfg.playNoise).toBeLessThanOrEqual(1);
      expect(Array.isArray(cfg.deviationRules)).toBe(true);
      expect(cfg.tiltSensitivity).toBeGreaterThanOrEqual(0);
      expect(cfg.tiltPlayImpact).toBeGreaterThanOrEqual(0);
      expect(typeof cfg.tiltBetImpact).toBe("number");
      expect(typeof cfg.usesCounter).toBe("boolean");
    }
  });

  it("counter uses the Hi-Lo counter", () => {
    expect(PERSONALITIES.counter.usesCounter).toBe(true);
    expect(PERSONALITIES.counter.betPolicy).toBe("kelly");
  });

  it("non-counter personalities do not use the counter", () => {
    for (const id of ALL_IDS) {
      if (id === "counter") continue;
      expect(PERSONALITIES[id].usesCounter).toBe(false);
    }
  });

  it("optimal has playNoise 0 and no deviations", () => {
    const opt = PERSONALITIES.optimal;
    expect(opt.playNoise).toBe(0);
    expect(opt.deviationRules).toHaveLength(0);
    expect(opt.tiltSensitivity).toBe(0);
  });

  it("chaser uses reverse-martingale and tilts bets upward", () => {
    expect(PERSONALITIES.chaser.betPolicy).toBe("reverse-martingale");
    expect(PERSONALITIES.chaser.tiltBetImpact).toBeGreaterThan(0);
  });

  it("risk_averse tilts bets downward", () => {
    expect(PERSONALITIES.risk_averse.tiltBetImpact).toBeLessThan(0);
  });

  it("superstitious has at least 2 deviations", () => {
    expect(PERSONALITIES.superstitious.deviationRules.length).toBeGreaterThanOrEqual(2);
  });

  it("deviation rules are well-formed", () => {
    const validWhen = new Set(["hard", "soft", "pair"]);
    const validOverride = new Set([
      "hit",
      "stand",
      "double",
      "split",
      "surrender",
    ]);
    for (const id of ALL_IDS) {
      for (const r of PERSONALITIES[id].deviationRules) {
        expect(validWhen.has(r.when)).toBe(true);
        expect(validOverride.has(r.override)).toBe(true);
        if (r.dealerUp !== undefined) {
          expect(r.dealerUp).toBeGreaterThanOrEqual(1);
          expect(r.dealerUp).toBeLessThanOrEqual(10);
        }
        if (r.playerTotal !== undefined) {
          expect(r.playerTotal).toBeGreaterThanOrEqual(1);
        }
      }
    }
  });
});
