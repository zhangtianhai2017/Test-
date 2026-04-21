/**
 * Client-to-server wire frames.
 *
 * Every frame:
 *   • carries `v: PROTOCOL_VERSION` (D-018)
 *   • carries a literal `type` matching one `ClientFrameType` entry
 *   • is `.strict()` so an unknown field is a validation error (catches typos
 *     between server and UE client during integration)
 *   • optionally carries `actionId` for idempotent action replay per the
 *     reconnect policy D-022
 *
 * To add a new frame, extend `ClientFrameType` in `frames.ts`, write its
 * schema here, then add it to `ClientFrame`'s discriminated union below.
 */

import { z } from "zod";

import {
  GestureSchema,
  LanguageSchema,
  NpcPersonalitySchema,
  PROTOCOL_VERSION,
  RuleSetIdSchema,
  SeatKindSchema,
  SideBetsSchema,
} from "./frames.js";

/**
 * Optional idempotency key shared by action frames. The client generates a
 * unique value for each action; if the same frame arrives twice (typically
 * after a reconnect) the server recognizes it and does not re-apply.
 *
 * Per D-022, reconnection within the 45 s grace window may replay actions.
 */
const actionId = z
  .string()
  .min(1)
  .max(64)
  .optional()
  .describe("Idempotency key for reconnect-safe action replay (D-022).");

// ---------------------------------------------------------------------------
// Session frames
// ---------------------------------------------------------------------------

export const HelloFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("HELLO"),
    displayName: z
      .string()
      .min(1)
      .max(32)
      .describe("Guest nickname (D-019; no login in v1)."),
    clientVersion: z.string().describe("Client build version string."),
    resumeSessionId: z
      .string()
      .optional()
      .describe("Previous sessionId for reconnect (D-022)."),
  })
  .strict();
export type HelloFrame = z.infer<typeof HelloFrame>;

export const PingFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("PING"),
    timestamp: z
      .number()
      .int()
      .optional()
      .describe("Client-side ms timestamp; echoed in PONG."),
  })
  .strict();
export type PingFrame = z.infer<typeof PingFrame>;

// ---------------------------------------------------------------------------
// Lobby / table management frames
// ---------------------------------------------------------------------------

export const ListTablesFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("LIST_TABLES"),
  })
  .strict();
export type ListTablesFrame = z.infer<typeof ListTablesFrame>;

export const CreateTableFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("CREATE_TABLE"),
    ruleSet: RuleSetIdSchema,
    maxSeats: z
      .number()
      .int()
      .min(1)
      .max(6)
      .default(6)
      .describe("Number of seats at the table; default 6 per D-007."),
    dealerPersona: z
      .string()
      .default("veteran")
      .describe("Dealer persona key for dealer-ai (D-003)."),
    language: LanguageSchema.default("zh").describe(
      "Table display/voice language (D-014).",
    ),
  })
  .strict();
export type CreateTableFrame = z.infer<typeof CreateTableFrame>;

export const JoinTableFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("JOIN_TABLE"),
    tableId: z.string().describe("Target table identifier."),
    seatRequest: z
      .array(z.number().int().min(0).max(5))
      .max(6)
      .optional()
      .describe(
        "Seat indices the client wishes to claim at join time (D-017; 1..6 seats per session).",
      ),
  })
  .strict();
export type JoinTableFrame = z.infer<typeof JoinTableFrame>;

export const LeaveTableFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("LEAVE_TABLE"),
  })
  .strict();
export type LeaveTableFrame = z.infer<typeof LeaveTableFrame>;

export const ConfigureTableFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("CONFIGURE_TABLE"),
    seats: z
      .array(
        z
          .object({
            kind: SeatKindSchema,
            name: z.string().optional(),
            personality: NpcPersonalitySchema.optional(),
            bankroll: z.number().int().nonnegative().optional(),
          })
          .strict(),
      )
      .max(6)
      .describe("Full seat configuration; replaces current seat layout."),
  })
  .strict();
export type ConfigureTableFrame = z.infer<typeof ConfigureTableFrame>;

export const ClaimSeatFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("CLAIM_SEAT"),
    seatIndex: z.number().int().min(0).max(5),
    name: z.string().min(1).max(32),
    bankroll: z
      .number()
      .int()
      .nonnegative()
      .optional()
      .describe("Optional buy-in override; defaults to rule-set starting bankroll."),
    actionId,
  })
  .strict();
export type ClaimSeatFrame = z.infer<typeof ClaimSeatFrame>;

export const ReleaseSeatFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("RELEASE_SEAT"),
    seatIndex: z.number().int().min(0).max(5),
    becomeNpc: z
      .boolean()
      .optional()
      .describe("If true, seat is handed off to an NPC driver (D-022 fallback)."),
    personality: NpcPersonalitySchema.optional(),
    actionId,
  })
  .strict();
export type ReleaseSeatFrame = z.infer<typeof ReleaseSeatFrame>;

// ---------------------------------------------------------------------------
// Round-action frames
// ---------------------------------------------------------------------------

export const PlaceBetFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("PLACE_BET"),
    seatIndex: z.number().int().min(0).max(5),
    amount: z.number().int().positive().describe("Main-bet chip amount."),
    sideBets: SideBetsSchema.optional(),
    actionId,
  })
  .strict();
export type PlaceBetFrame = z.infer<typeof PlaceBetFrame>;

export const HitFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("HIT"),
    seatIndex: z.number().int().min(0).max(5),
    actionId,
  })
  .strict();
export type HitFrame = z.infer<typeof HitFrame>;

export const StandFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("STAND"),
    seatIndex: z.number().int().min(0).max(5),
    actionId,
  })
  .strict();
export type StandFrame = z.infer<typeof StandFrame>;

export const DoubleFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("DOUBLE"),
    seatIndex: z.number().int().min(0).max(5),
    actionId,
  })
  .strict();
export type DoubleFrame = z.infer<typeof DoubleFrame>;

export const SplitFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("SPLIT"),
    seatIndex: z.number().int().min(0).max(5),
    actionId,
  })
  .strict();
export type SplitFrame = z.infer<typeof SplitFrame>;

export const SurrenderFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("SURRENDER"),
    seatIndex: z.number().int().min(0).max(5),
    actionId,
  })
  .strict();
export type SurrenderFrame = z.infer<typeof SurrenderFrame>;

export const InsureFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("INSURE"),
    seatIndex: z.number().int().min(0).max(5),
    amount: z
      .number()
      .int()
      .nonnegative()
      .describe("Insurance chip amount (0..floor(bet/2))."),
    actionId,
  })
  .strict();
export type InsureFrame = z.infer<typeof InsureFrame>;

export const DeclineInsuranceFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("DECLINE_INSURANCE"),
    seatIndex: z.number().int().min(0).max(5),
    actionId,
  })
  .strict();
export type DeclineInsuranceFrame = z.infer<typeof DeclineInsuranceFrame>;

export const GestureFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("GESTURE"),
    seatIndex: z.number().int().min(0).max(5),
    gesture: GestureSchema,
    actionId,
  })
  .strict();
export type GestureFrame = z.infer<typeof GestureFrame>;

export const NewRoundFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("NEW_ROUND"),
    actionId,
  })
  .strict();
export type NewRoundFrame = z.infer<typeof NewRoundFrame>;

// ---------------------------------------------------------------------------
// Discriminated union + inferred type
// ---------------------------------------------------------------------------

/**
 * The full client-to-server frame union. Use `ClientFrame.parse(unknown)` at
 * the server boundary; the resulting value is narrowed to the correct frame
 * schema by `type`.
 */
export const ClientFrame = z.discriminatedUnion("type", [
  HelloFrame,
  ListTablesFrame,
  CreateTableFrame,
  JoinTableFrame,
  LeaveTableFrame,
  ConfigureTableFrame,
  ClaimSeatFrame,
  ReleaseSeatFrame,
  PlaceBetFrame,
  HitFrame,
  StandFrame,
  DoubleFrame,
  SplitFrame,
  SurrenderFrame,
  InsureFrame,
  DeclineInsuranceFrame,
  GestureFrame,
  NewRoundFrame,
  PingFrame,
]);
export type ClientFrame = z.infer<typeof ClientFrame>;
