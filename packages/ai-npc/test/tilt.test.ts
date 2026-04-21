import { describe, it, expect } from "vitest";
import { updateTilt, passiveDecay, DEFAULT_TILT } from "../src/tilt.js";

describe("updateTilt", () => {
  it("increases tilt on a loss", () => {
    const next = updateTilt(0.2, "loss", -1, 1);
    expect(next).toBeGreaterThan(0.2);
  });

  it("increases tilt on a bust", () => {
    const next = updateTilt(0.2, "bust", -1, 1);
    // bust bump > loss bump per DEFAULT_TILT
    expect(next).toBeGreaterThan(0.2 + DEFAULT_TILT.lossBump - 0.0001);
  });

  it("increases tilt on surrender", () => {
    const next = updateTilt(0.2, "surrender", -0.5, 1);
    expect(next).toBeGreaterThan(0.2);
  });

  it("adds a bigLossBump when netDelta exceeds threshold", () => {
    const small = updateTilt(0.1, "loss", -1, 1);
    const big = updateTilt(0.1, "loss", -4, 1); // threshold is 2 units
    expect(big).toBeGreaterThan(small);
  });

  it("decreases tilt on a win", () => {
    const next = updateTilt(0.5, "win", 1, 1);
    expect(next).toBeLessThan(0.5);
  });

  it("treats blackjack like a win", () => {
    const next = updateTilt(0.5, "blackjack", 1.5, 1);
    expect(next).toBeLessThan(0.5);
  });

  it("decreases tilt on push (by pushDecay only, not passive decay)", () => {
    const start = 0.5;
    const next = updateTilt(start, "push", 0, 1);
    expect(next).toBeCloseTo(start - DEFAULT_TILT.pushDecay, 10);
  });

  it("clamps to [0, 1]", () => {
    // Push below 0
    const low = updateTilt(0.01, "win", 1, 1);
    expect(low).toBeGreaterThanOrEqual(0);
    // Push above 1 with repeated bumps
    let t = 0.95;
    for (let i = 0; i < 10; i++) {
      t = updateTilt(t, "bust", -10, 1);
    }
    expect(t).toBeLessThanOrEqual(1);
  });

  it("scales deltas by sensitivity", () => {
    const stoic = updateTilt(0.3, "loss", -1, 1, { sensitivity: 0 });
    expect(stoic).toBe(0.3);
    const twitchy = updateTilt(0.3, "loss", -1, 1, { sensitivity: 2 });
    const normal = updateTilt(0.3, "loss", -1, 1, { sensitivity: 1 });
    expect(twitchy - 0.3).toBeCloseTo(2 * (normal - 0.3), 10);
  });

  it("is deterministic for the same inputs", () => {
    const a = updateTilt(0.4, "loss", -3, 1);
    const b = updateTilt(0.4, "loss", -3, 1);
    expect(a).toBe(b);
  });
});

describe("passiveDecay", () => {
  it("reduces tilt by passiveDecayPerRound × sensitivity", () => {
    const next = passiveDecay(0.5);
    expect(next).toBeCloseTo(0.5 - DEFAULT_TILT.passiveDecayPerRound, 10);
  });

  it("clamps to minTilt", () => {
    const next = passiveDecay(0.01);
    expect(next).toBeGreaterThanOrEqual(0);
  });

  it("passive decay is independent of outcome-driven updates", () => {
    // push applies pushDecay, not passive decay
    const pushed = updateTilt(0.5, "push", 0, 1);
    const passive = passiveDecay(0.5);
    expect(pushed).not.toBe(passive);
  });
});
