import { describe, it, expect } from "vitest";

import {
  CardDealtFrame,
  ClientFrame,
  HelloFrame,
  HitFrame,
  JoinTableFrame,
  PROTOCOL_VERSION,
  ServerFrame,
  TableStateFrame,
} from "../src/protocol/index.js";

describe("protocol: client frames", () => {
  it("parses a valid HELLO frame", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "HELLO" as const,
      displayName: "Alice",
      clientVersion: "0.1.0",
    };
    const parsed = HelloFrame.parse(raw);
    expect(parsed.displayName).toBe("Alice");
    expect(parsed.type).toBe("HELLO");
  });

  it("rejects HELLO missing displayName", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "HELLO",
      clientVersion: "0.1.0",
    };
    const result = HelloFrame.safeParse(raw);
    expect(result.success).toBe(false);
  });

  it("rejects HELLO with unknown fields (strict)", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "HELLO",
      displayName: "Alice",
      clientVersion: "0.1.0",
      bogus: true,
    };
    const result = HelloFrame.safeParse(raw);
    expect(result.success).toBe(false);
  });

  it("rejects JOIN_TABLE with seatRequest of 7 elements (max 6)", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "JOIN_TABLE",
      tableId: "t1",
      seatRequest: [0, 1, 2, 3, 4, 5, 0],
    };
    const result = JoinTableFrame.safeParse(raw);
    expect(result.success).toBe(false);
  });

  it("JOIN_TABLE with seatRequest of 6 elements is accepted", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "JOIN_TABLE",
      tableId: "t1",
      seatRequest: [0, 1, 2, 3, 4, 5],
    };
    const parsed = JoinTableFrame.parse(raw);
    expect(parsed.seatRequest?.length).toBe(6);
  });

  it("discriminated union narrows HIT frame to HitFrame shape", () => {
    const raw = { v: PROTOCOL_VERSION, type: "HIT", seatIndex: 0 };
    const parsed = ClientFrame.parse(raw);
    // At runtime we can inspect .type; at the type level, this is narrowed.
    if (parsed.type === "HIT") {
      const h: HitFrame = parsed;
      expect(h.seatIndex).toBe(0);
    } else {
      throw new Error("Expected HIT discriminant");
    }
  });

  it("round-trips a valid ClientFrame through JSON", () => {
    const original = {
      v: PROTOCOL_VERSION,
      type: "PLACE_BET" as const,
      seatIndex: 2,
      amount: 50,
      sideBets: { perfectPairs: 5 },
      actionId: "act-123",
    };
    const parsedA = ClientFrame.parse(original);
    const encoded = JSON.stringify(parsedA);
    const decoded = JSON.parse(encoded);
    const parsedB = ClientFrame.parse(decoded);
    expect(parsedB).toEqual(parsedA);
  });

  it("rejects a frame with the wrong protocol version", () => {
    const raw = {
      v: 99,
      type: "HELLO",
      displayName: "Alice",
      clientVersion: "0.1.0",
    };
    const result = ClientFrame.safeParse(raw);
    expect(result.success).toBe(false);
  });
});

describe("protocol: server frames (face-down invariant)", () => {
  it("CARD_DEALT with faceDown=true and no card is valid", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "CARD_DEALT",
      to: "dealer",
      handIndex: 0,
      faceDown: true,
    };
    const parsed = CardDealtFrame.parse(raw);
    expect(parsed.faceDown).toBe(true);
    expect((parsed as { card?: unknown }).card).toBeUndefined();
  });

  it("CARD_DEALT with faceDown=true AND a card is rejected (card must be withheld)", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "CARD_DEALT",
      to: "dealer",
      handIndex: 0,
      card: { rank: "A", suit: "♠" },
      faceDown: true,
    };
    const result = CardDealtFrame.safeParse(raw);
    expect(result.success).toBe(false);
  });

  it("CARD_DEALT with faceDown=false and no card is rejected", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "CARD_DEALT",
      to: "player",
      seatIndex: 0,
      handIndex: 0,
      faceDown: false,
    };
    const result = CardDealtFrame.safeParse(raw);
    expect(result.success).toBe(false);
  });

  it("CARD_DEALT with faceDown=false and a card is valid", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "CARD_DEALT",
      to: "player",
      seatIndex: 1,
      handIndex: 0,
      card: { rank: "K", suit: "♥" },
      faceDown: false,
    };
    const parsed = CardDealtFrame.parse(raw);
    expect(parsed.card?.rank).toBe("K");
  });

  it("CARD_DEALT to player without seatIndex is rejected", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "CARD_DEALT",
      to: "player",
      handIndex: 0,
      card: { rank: "5", suit: "♦" },
      faceDown: false,
    };
    const result = CardDealtFrame.safeParse(raw);
    expect(result.success).toBe(false);
  });
});

describe("protocol: server TABLE_STATE", () => {
  it("hides hole with placeholder when holeHidden is true", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "TABLE_STATE",
      tableId: "t1",
      phase: "playerTurn",
      ruleSet: "VEGAS",
      language: "zh",
      dealerPersona: "veteran",
      seats: [],
      dealer: {
        cards: [
          { rank: "9", suit: "♣" },
          { faceDown: true },
        ],
        total: 9,
        soft: false,
        isBust: false,
        holeHidden: true,
      },
      activeSeatIndex: 0,
      maxSeats: 6,
    };
    const parsed = TableStateFrame.parse(raw);
    expect(parsed.dealer.cards).toHaveLength(2);
    expect(parsed.dealer.holeHidden).toBe(true);
  });

  it("ServerFrame union routes TABLE_STATE correctly", () => {
    const raw = {
      v: PROTOCOL_VERSION,
      type: "TABLE_STATE",
      tableId: "t1",
      phase: "betting",
      ruleSet: "VEGAS",
      language: "en",
      dealerPersona: "veteran",
      seats: [],
      dealer: {
        cards: [],
        total: 0,
        soft: false,
        isBust: false,
        holeHidden: false,
      },
      activeSeatIndex: null,
      maxSeats: 6,
    };
    const parsed = ServerFrame.parse(raw);
    expect(parsed.type).toBe("TABLE_STATE");
  });
});
