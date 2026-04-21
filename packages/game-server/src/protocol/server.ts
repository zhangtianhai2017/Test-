/**
 * Server-to-client wire frames.
 *
 * Every frame:
 *   • carries `v: PROTOCOL_VERSION` (D-018)
 *   • carries a literal `type` matching one `ServerFrameType` entry
 *   • is `.strict()` so an unknown field is a validation error (catches typos
 *     between server and UE client during integration)
 *
 * Critical invariants enforced by these schemas (game-server AGENT.md §Key
 * invariants):
 *   - Hole cards are NEVER broadcast. `CARD_DEALT` with `faceDown: true` omits
 *     `card` entirely; the contents become visible only via a subsequent
 *     `HOLE_CARD_REVEALED` frame.
 *   - `TABLE_STATE` is an authoritative snapshot. When the dealer's hole card
 *     is still hidden, its slot in `dealer.cards` is the `HiddenCard`
 *     placeholder `{faceDown: true}` — never the real rank/suit.
 *   - Seat-indexed events (`BET_SETTLED`, `HAND_BUST`, `NATURAL_BLACKJACK`,
 *     `GESTURE_MADE`) always include `seatIndex` so multi-seat clients can
 *     route the event to the right render slot (D-007, D-017).
 *
 * To add a new frame, extend `ServerFrameType` in `frames.ts`, write its
 * schema here, then add it to `ServerFrame`'s discriminated union below.
 */

import { z } from "zod";

import {
  CardPayload,
  GestureSchema,
  LanguageSchema,
  NpcPersonalitySchema,
  OutcomeSchema,
  PROTOCOL_VERSION,
  PhaseSchema,
  RuleSetIdSchema,
  SeatKindSchema,
  SideBetsSchema,
} from "./frames.js";

// ---------------------------------------------------------------------------
// Shared server-side payload shapes
// ---------------------------------------------------------------------------

/**
 * Placeholder for a card the server is withholding (typically the dealer's
 * hole card during `playerTurn`). Always `{faceDown: true}`; contains no
 * rank/suit so a malicious or buggy client cannot leak it.
 */
export const HiddenCard = z
  .object({
    faceDown: z.literal(true),
  })
  .strict()
  .describe("Face-down card placeholder; no rank/suit ever sent.");
export type HiddenCard = z.infer<typeof HiddenCard>;

/**
 * Either a real card or the face-down placeholder. Used inside the dealer
 * hand array in `TABLE_STATE`.
 */
export const MaybeHiddenCard = z.union([CardPayload, HiddenCard]);
export type MaybeHiddenCard = z.infer<typeof MaybeHiddenCard>;

/**
 * A single hand inside a seat. Mirrors engine `PlayerHand` but omits
 * server-internal flags the client does not need.
 */
export const HandPayload = z
  .object({
    handIndex: z.number().int().nonnegative(),
    cards: z.array(CardPayload).describe("Cards in this hand; all visible."),
    bet: z.number().int().nonnegative(),
    doubled: z.boolean(),
    surrendered: z.boolean(),
    stood: z.boolean(),
    splitFromAces: z.boolean(),
    total: z
      .number()
      .int()
      .describe("Best hand total (soft-ace resolved)."),
    soft: z.boolean().describe("True if total counts an ace as 11."),
    isBust: z.boolean(),
  })
  .strict();
export type HandPayload = z.infer<typeof HandPayload>;

/**
 * Public view of a seat inside `TABLE_STATE`. `ownerSessionId` is present so
 * the claiming client can see which seats it controls; other clients use it
 * only as an opaque identifier (D-017, D-019).
 */
export const SeatPayload = z
  .object({
    index: z.number().int().min(0).max(5),
    kind: SeatKindSchema,
    playerName: z.string(),
    bankroll: z.number().int().nonnegative(),
    personality: NpcPersonalitySchema.optional(),
    ownerSessionId: z.string().nullable(),
    hands: z.array(HandPayload),
    activeHandIndex: z.number().int().nonnegative(),
    pendingBet: z.number().int().nonnegative(),
    sideBets: SideBetsSchema,
    insuranceBet: z.number().int().nonnegative(),
    gestures: z.array(GestureSchema),
    tilt: z.number(),
  })
  .strict();
export type SeatPayload = z.infer<typeof SeatPayload>;

/**
 * Public view of the dealer. Cards are a mix of visible cards and the hidden
 * placeholder during the player's turn. After `HOLE_CARD_REVEALED`, all
 * entries are visible.
 */
export const DealerPayload = z
  .object({
    cards: z.array(MaybeHiddenCard),
    total: z
      .number()
      .int()
      .describe("Total of VISIBLE dealer cards only; excludes hidden hole."),
    soft: z.boolean(),
    isBust: z.boolean(),
    holeHidden: z.boolean(),
  })
  .strict();
export type DealerPayload = z.infer<typeof DealerPayload>;

/**
 * A single lobby table summary returned in `TABLE_LIST`.
 */
export const TableSummary = z
  .object({
    tableId: z.string(),
    ruleSet: RuleSetIdSchema,
    maxSeats: z.number().int().min(1).max(6),
    seatsTaken: z.number().int().min(0).max(6),
    phase: PhaseSchema,
    language: LanguageSchema,
    dealerPersona: z.string(),
  })
  .strict();
export type TableSummary = z.infer<typeof TableSummary>;

/**
 * Settlement result for a single hand; carried inside `ROUND_OVER`.
 */
export const HandResultPayload = z
  .object({
    seatIndex: z.number().int().min(0).max(5),
    handIndex: z.number().int().nonnegative(),
    outcome: OutcomeSchema,
    payout: z.number().int().nonnegative(),
    total: z.number().int(),
    label: z.string().optional(),
  })
  .strict();
export type HandResultPayload = z.infer<typeof HandResultPayload>;

// ---------------------------------------------------------------------------
// Session frames
// ---------------------------------------------------------------------------

export const WelcomeFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("WELCOME"),
    sessionId: z
      .string()
      .describe("Server-assigned session UUID (D-019)."),
    serverVersion: z.string(),
    reconnectGraceSeconds: z
      .number()
      .int()
      .nonnegative()
      .describe("Seconds the server holds seats after disconnect (D-022; ≈ 45)."),
  })
  .strict();
export type WelcomeFrame = z.infer<typeof WelcomeFrame>;

export const ErrorFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("ERROR"),
    code: z
      .string()
      .describe("Stable error code (e.g. ILLEGAL_ACTION, BAD_SEAT_INDEX)."),
    message: z.string().describe("Human-readable error detail."),
    actionIdRef: z
      .string()
      .optional()
      .describe("Echoes the client's actionId, if the error was triggered by one."),
  })
  .strict();
export type ErrorFrame = z.infer<typeof ErrorFrame>;

export const PongFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("PONG"),
    timestamp: z
      .number()
      .int()
      .optional()
      .describe("Echo of the PING's timestamp, if provided."),
    serverTime: z
      .number()
      .int()
      .optional()
      .describe("Server wall-clock ms, useful for latency estimates."),
  })
  .strict();
export type PongFrame = z.infer<typeof PongFrame>;

export const SessionLostFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("SESSION_LOST"),
    reason: z
      .enum(["grace-expired", "kicked", "shutdown", "duplicate-login"])
      .describe("Why the server is dropping the session (D-022)."),
    message: z.string().optional(),
  })
  .strict();
export type SessionLostFrame = z.infer<typeof SessionLostFrame>;

// ---------------------------------------------------------------------------
// Lobby / table management frames
// ---------------------------------------------------------------------------

export const TableListFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("TABLE_LIST"),
    tables: z.array(TableSummary),
  })
  .strict();
export type TableListFrame = z.infer<typeof TableListFrame>;

export const TableCreatedFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("TABLE_CREATED"),
    table: TableSummary,
  })
  .strict();
export type TableCreatedFrame = z.infer<typeof TableCreatedFrame>;

export const TableStateFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("TABLE_STATE"),
    tableId: z.string(),
    phase: PhaseSchema,
    ruleSet: RuleSetIdSchema,
    language: LanguageSchema,
    dealerPersona: z.string(),
    seats: z.array(SeatPayload).max(6),
    dealer: DealerPayload,
    activeSeatIndex: z
      .number()
      .int()
      .min(0)
      .max(5)
      .nullable()
      .describe("Seat whose turn it is during playerTurn phase."),
    maxSeats: z.number().int().min(1).max(6),
  })
  .strict();
export type TableStateFrame = z.infer<typeof TableStateFrame>;

/**
 * Lightweight incremental update to a previously broadcast `TABLE_STATE`.
 * We don't dictate a strict patch format here — the server sends a set of
 * field-level changes and the client merges. This keeps M3c free to iterate
 * on the diff shape without a protocol version bump.
 */
export const TableDeltaFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("TABLE_DELTA"),
    tableId: z.string(),
    seq: z
      .number()
      .int()
      .nonnegative()
      .describe("Monotonic server sequence; client resyncs on gap."),
    patch: z
      .record(z.unknown())
      .describe("Shallow merge patch against the last TABLE_STATE."),
  })
  .strict();
export type TableDeltaFrame = z.infer<typeof TableDeltaFrame>;

export const SeatAssignedFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("SEAT_ASSIGNED"),
    seatIndex: z.number().int().min(0).max(5),
    ownerSessionId: z.string(),
    playerName: z.string(),
    bankroll: z.number().int().nonnegative(),
  })
  .strict();
export type SeatAssignedFrame = z.infer<typeof SeatAssignedFrame>;

export const SeatReleasedFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("SEAT_RELEASED"),
    seatIndex: z.number().int().min(0).max(5),
    becameNpc: z.boolean().optional(),
    personality: NpcPersonalitySchema.optional(),
  })
  .strict();
export type SeatReleasedFrame = z.infer<typeof SeatReleasedFrame>;

// ---------------------------------------------------------------------------
// Round / card-level frames
// ---------------------------------------------------------------------------

export const PhaseChangedFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("PHASE_CHANGED"),
    phase: PhaseSchema,
    activeSeatIndex: z
      .number()
      .int()
      .min(0)
      .max(5)
      .nullable()
      .optional()
      .describe("New active seat, if phase transition implies one."),
  })
  .strict();
export type PhaseChangedFrame = z.infer<typeof PhaseChangedFrame>;

/**
 * A card was dealt. CRITICAL: when `faceDown` is true the server withholds
 * `card` entirely — the rank/suit does not travel over the wire until a
 * later `HOLE_CARD_REVEALED` frame. This is enforced by `.superRefine`
 * below.
 */
export const CardDealtFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("CARD_DEALT"),
    to: z.enum(["player", "dealer"]),
    seatIndex: z
      .number()
      .int()
      .min(0)
      .max(5)
      .optional()
      .describe("Present when to='player'; absent for dealer deals."),
    handIndex: z.number().int().nonnegative(),
    card: CardPayload
      .optional()
      .describe("Omitted when faceDown=true; present otherwise."),
    faceDown: z.boolean(),
  })
  .strict()
  .superRefine((frame, ctx) => {
    if (frame.faceDown && frame.card !== undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["card"],
        message:
          "Face-down deals must NOT include card rank/suit (server-side invariant).",
      });
    }
    if (!frame.faceDown && frame.card === undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["card"],
        message: "Face-up deals must include the card payload.",
      });
    }
    if (frame.to === "player" && frame.seatIndex === undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["seatIndex"],
        message: "Player deals require seatIndex.",
      });
    }
  });
export type CardDealtFrame = z.infer<typeof CardDealtFrame>;

/**
 * Reveals a previously-hidden card. Ends the face-down contract for that
 * card; the client should patch its local state accordingly.
 */
export const HoleCardRevealedFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("HOLE_CARD_REVEALED"),
    card: CardPayload,
    cardIndex: z
      .number()
      .int()
      .nonnegative()
      .default(1)
      .describe("Position in dealer.cards; the hole is always index 1."),
  })
  .strict();
export type HoleCardRevealedFrame = z.infer<typeof HoleCardRevealedFrame>;

export const PlayerActionFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("PLAYER_ACTION"),
    seatIndex: z.number().int().min(0).max(5),
    handIndex: z.number().int().nonnegative(),
    action: z.enum(["HIT", "STAND", "DOUBLE", "SPLIT", "SURRENDER"]),
    actionIdRef: z.string().optional(),
  })
  .strict();
export type PlayerActionFrame = z.infer<typeof PlayerActionFrame>;

export const HandBustFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("HAND_BUST"),
    seatIndex: z.number().int().min(0).max(5),
    handIndex: z.number().int().nonnegative(),
    total: z.number().int(),
  })
  .strict();
export type HandBustFrame = z.infer<typeof HandBustFrame>;

export const NaturalBlackjackFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("NATURAL_BLACKJACK"),
    seatIndex: z.number().int().min(0).max(5),
    handIndex: z.number().int().nonnegative(),
  })
  .strict();
export type NaturalBlackjackFrame = z.infer<typeof NaturalBlackjackFrame>;

export const DealerActionFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("DEALER_ACTION"),
    action: z.enum(["HIT", "STAND"]),
    total: z.number().int(),
    soft: z.boolean(),
  })
  .strict();
export type DealerActionFrame = z.infer<typeof DealerActionFrame>;

export const BetSettledFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("BET_SETTLED"),
    seatIndex: z.number().int().min(0).max(5),
    handIndex: z.number().int().nonnegative(),
    outcome: OutcomeSchema,
    payout: z.number().int().nonnegative(),
    label: z.string().optional(),
  })
  .strict();
export type BetSettledFrame = z.infer<typeof BetSettledFrame>;

export const RoundOverFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("ROUND_OVER"),
    results: z.array(HandResultPayload),
  })
  .strict();
export type RoundOverFrame = z.infer<typeof RoundOverFrame>;

export const BankrollChangedFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("BANKROLL_CHANGED"),
    seatIndex: z.number().int().min(0).max(5),
    bankroll: z.number().int().nonnegative(),
    delta: z.number().int(),
  })
  .strict();
export type BankrollChangedFrame = z.infer<typeof BankrollChangedFrame>;

export const SidebetWinFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("SIDEBET_WIN"),
    seatIndex: z.number().int().min(0).max(5),
    kind: z.enum(["perfectPairs", "21+3", "luckyLadies"]),
    payout: z.number().int().nonnegative(),
    label: z.string(),
  })
  .strict();
export type SidebetWinFrame = z.infer<typeof SidebetWinFrame>;

export const ShoeShuffledFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("SHOE_SHUFFLED"),
  })
  .strict();
export type ShoeShuffledFrame = z.infer<typeof ShoeShuffledFrame>;

export const GestureMadeFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("GESTURE_MADE"),
    seatIndex: z.number().int().min(0).max(5),
    gesture: GestureSchema,
  })
  .strict();
export type GestureMadeFrame = z.infer<typeof GestureMadeFrame>;

// ---------------------------------------------------------------------------
// Dealer AI frames (text + audio carried separately)
// ---------------------------------------------------------------------------

/**
 * Dealer quip text. Tone and language come directly from the dealer-ai
 * service (D-003, D-014). Audio is optional; when TTS is disabled or CPU-
 * only fallback is active, `audioUrl` is absent per D-011.
 */
export const DealerQuipFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("DEALER_QUIP"),
    text: z.string(),
    tone: z
      .string()
      .describe("Dealer tone tag from dealer-ai (e.g. 'neutral', 'pressuring')."),
    language: LanguageSchema,
    audioUrl: z
      .string()
      .optional()
      .describe("Optional URL to CosyVoice-rendered audio (D-011)."),
    persona: z.string().optional(),
  })
  .strict();
export type DealerQuipFrame = z.infer<typeof DealerQuipFrame>;

/**
 * Out-of-band audio broadcast; decoupled from `DEALER_QUIP` so the server
 * may deliver pre-rendered audio clips (e.g. ambience, cheers) that aren't
 * tied to a text quip.
 */
export const DealerAudioFrame = z
  .object({
    v: z.literal(PROTOCOL_VERSION),
    type: z.literal("DEALER_AUDIO"),
    audioUrl: z.string(),
    durationMs: z.number().int().nonnegative().optional(),
    kind: z
      .enum(["quip", "ambience", "sfx"])
      .default("quip")
      .describe("Classifier so the client can choose a mixing bus."),
  })
  .strict();
export type DealerAudioFrame = z.infer<typeof DealerAudioFrame>;

// ---------------------------------------------------------------------------
// Discriminated union + inferred type
// ---------------------------------------------------------------------------

/**
 * The full server-to-client frame union. Clients parse incoming messages via
 * `ServerFrame.parse(unknown)`; the result is narrowed by `type`.
 *
 * NOTE: `CardDealtFrame` uses `.superRefine` and therefore is a ZodEffects
 * rather than a plain ZodObject. `z.discriminatedUnion` requires the members
 * to be ZodObjects, so we use a plain `z.union` here instead. Runtime
 * behavior is equivalent (parse narrows on `type`), with a slightly higher
 * cost since zod tries each branch until one matches. Given the size of
 * this union and card-game throughput, the cost is negligible.
 */
export const ServerFrame = z.union([
  WelcomeFrame,
  ErrorFrame,
  TableListFrame,
  TableCreatedFrame,
  TableStateFrame,
  TableDeltaFrame,
  SeatAssignedFrame,
  SeatReleasedFrame,
  PhaseChangedFrame,
  CardDealtFrame,
  HoleCardRevealedFrame,
  PlayerActionFrame,
  HandBustFrame,
  NaturalBlackjackFrame,
  DealerActionFrame,
  BetSettledFrame,
  RoundOverFrame,
  BankrollChangedFrame,
  SidebetWinFrame,
  ShoeShuffledFrame,
  GestureMadeFrame,
  DealerQuipFrame,
  DealerAudioFrame,
  SessionLostFrame,
  PongFrame,
]);
export type ServerFrame = z.infer<typeof ServerFrame>;
