/**
 * Wire protocol — envelope + message-type enumeration.
 *
 * Per D-018: WebSocket transport, JSON message envelope, every frame carries
 * `{v: 1, type, ...}` so a v2 can be introduced without breaking v1 clients.
 *
 * Schemas in this directory are the canonical source of truth; the UE client
 * must mirror them exactly. See `client.ts` / `server.ts` for per-frame
 * schemas, and `index.ts` for the barrel re-export used by consumers.
 */

import { z } from "zod";

/**
 * Protocol version literal. Server and clients refuse frames that don't
 * carry this exact value. Bumping this intentionally is a breaking change
 * and must go through PM per the escalation rules in AGENT.md.
 */
export const PROTOCOL_VERSION = 1 as const;

/**
 * Enumerates every client-to-server frame. Adding a new entry here forces
 * adding a matching schema in `client.ts` and a branch in `ClientFrame`.
 */
export const ClientFrameType = z.enum([
  "HELLO",
  "LIST_TABLES",
  "CREATE_TABLE",
  "JOIN_TABLE",
  "LEAVE_TABLE",
  "CONFIGURE_TABLE",
  "CLAIM_SEAT",
  "RELEASE_SEAT",
  "PLACE_BET",
  "HIT",
  "STAND",
  "DOUBLE",
  "SPLIT",
  "SURRENDER",
  "INSURE",
  "DECLINE_INSURANCE",
  "GESTURE",
  "NEW_ROUND",
  "PING",
]);
export type ClientFrameType = z.infer<typeof ClientFrameType>;

/**
 * Enumerates every server-to-client frame. Adding a new entry here forces
 * adding a matching schema in `server.ts` and a branch in `ServerFrame`.
 */
export const ServerFrameType = z.enum([
  "WELCOME",
  "ERROR",
  "TABLE_LIST",
  "TABLE_CREATED",
  "TABLE_STATE",
  "TABLE_DELTA",
  "SEAT_ASSIGNED",
  "SEAT_RELEASED",
  "PHASE_CHANGED",
  "CARD_DEALT",
  "HOLE_CARD_REVEALED",
  "PLAYER_ACTION",
  "HAND_BUST",
  "NATURAL_BLACKJACK",
  "DEALER_ACTION",
  "BET_SETTLED",
  "ROUND_OVER",
  "BANKROLL_CHANGED",
  "SIDEBET_WIN",
  "SHOE_SHUFFLED",
  "GESTURE_MADE",
  "DEALER_QUIP",
  "DEALER_AUDIO",
  "SESSION_LOST",
  "PONG",
]);
export type ServerFrameType = z.infer<typeof ServerFrameType>;

// ---------------------------------------------------------------------------
// Shared value schemas — referenced by both client and server frames.
// ---------------------------------------------------------------------------

/**
 * Card rank. Mirrors the engine's `Rank` type (`packages/engine/src/cards.ts`).
 * Kept as a string union here rather than importing the engine type so the
 * schema can be emitted for the UE client without pulling engine internals.
 */
export const RankSchema = z
  .enum(["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"])
  .describe("Card rank. Mirrors engine Rank.");

/**
 * Card suit (Unicode glyphs, matching the engine).
 */
export const SuitSchema = z
  .enum(["♠", "♥", "♦", "♣"]) // ♠ ♥ ♦ ♣
  .describe("Card suit glyph.");

/**
 * Single card payload. Shared by `CARD_DEALT`, `HOLE_CARD_REVEALED`, and the
 * dealer/player hand arrays inside `TABLE_STATE`. The server omits this
 * entirely on face-down cards — see `CardDealtFrame` in `server.ts`.
 */
export const CardPayload = z
  .object({
    rank: RankSchema,
    suit: SuitSchema,
  })
  .strict()
  .describe("A single visible card.");
export type CardPayload = z.infer<typeof CardPayload>;

/**
 * Gesture vocabulary shared by client `GESTURE` and server `GESTURE_MADE`.
 * Mirrors the engine `Gesture` type.
 */
export const GestureSchema = z
  .enum(["confident", "nervous", "poker-face", "taunt", "sigh", "celebrate"])
  .describe("Player-expression gesture.");
export type GestureSchema = z.infer<typeof GestureSchema>;

/**
 * Rule-set identifier, mirrors engine `RuleSetId`.
 */
export const RuleSetIdSchema = z
  .enum(["VEGAS", "SPANISH21", "PONTOON", "SUPER_FUN_21"])
  .describe("Rule-set identifier, mirrors engine RuleSetId.");
export type RuleSetIdSchema = z.infer<typeof RuleSetIdSchema>;

/**
 * NPC personality; mirrors engine `NpcPersonality`.
 */
export const NpcPersonalitySchema = z
  .enum([
    "optimal",
    "counter",
    "amateur",
    "chaser",
    "superstitious",
    "ritualistic",
    "risk_averse",
  ])
  .describe("NPC personality key.");
export type NpcPersonalitySchema = z.infer<typeof NpcPersonalitySchema>;

/**
 * Seat kind enum; mirrors engine `SeatKind`.
 */
export const SeatKindSchema = z
  .enum(["empty", "human", "npc"])
  .describe("Seat occupancy kind.");
export type SeatKindSchema = z.infer<typeof SeatKindSchema>;

/**
 * Phase enum; mirrors engine `Phase`.
 */
export const PhaseSchema = z
  .enum([
    "betting",
    "dealing",
    "insurance",
    "playerTurn",
    "dealerTurn",
    "settlement",
    "roundOver",
  ])
  .describe("Round phase.");
export type PhaseSchema = z.infer<typeof PhaseSchema>;

/**
 * Outcome enum; mirrors engine `Outcome`.
 */
export const OutcomeSchema = z
  .enum(["win", "loss", "push", "blackjack", "surrender", "bust"])
  .describe("Hand outcome at settlement.");
export type OutcomeSchema = z.infer<typeof OutcomeSchema>;

/**
 * Supported interface languages for dealer text/voice. Per D-014 the choice
 * is made at session/table start; this value rides on `DEALER_QUIP` frames.
 */
export const LanguageSchema = z
  .enum(["zh", "en"])
  .describe("UI / dealer language.");
export type LanguageSchema = z.infer<typeof LanguageSchema>;

/**
 * Side-bet amounts, mirrors engine `SideBets`. Amounts are chip integers.
 */
export const SideBetsSchema = z
  .object({
    perfectPairs: z.number().int().nonnegative().optional(),
    twentyOneP3: z.number().int().nonnegative().optional(),
    luckyLadies: z.number().int().nonnegative().optional(),
  })
  .strict()
  .describe("Optional side-bet amounts.");
export type SideBetsSchema = z.infer<typeof SideBetsSchema>;
