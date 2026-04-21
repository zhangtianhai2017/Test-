# DECISIONS — append-only log

> Every confirmed decision goes here with a unique ID and date. Never edit a
> past entry; supersede with a new one if it changes. This is the authority
> for disputes about "what was agreed".

Format per entry:

```
## D-NNN — short title
Date: YYYY-MM-DD
Status: confirmed | superseded by D-MMM
Context: one paragraph
Decision: one paragraph
Affects: <modules>
```

---

## D-001 — Product is casino-style Blackjack 21, not just mechanics
Date: 2026-04-19
Status: confirmed
Context: Initial ask — a full Blackjack game, not a toy.
Decision: Support Classic Vegas (H17), Spanish 21, Pontoon, Super Fun 21,
plus side bets 21+3, Perfect Pairs, Lucky Ladies. Full action set: hit,
stand, double, split (with DAS), surrender, insurance.
Affects: `engine`, `ue-plugin`

## D-002 — Headless rules engine, multiple pluggable front-ends
Date: 2026-04-19
Status: confirmed
Context: Engine must be swappable across UI stacks.
Decision: Pure TypeScript `engine` package with zero DOM/Three.js/UE
dependencies. All front-ends interact via a single action/event API.
Affects: `engine`, `ui-web`, `ui-3d`, `ue-plugin`

## D-003 — Dealer intelligence is *conversational*, not strategic
Date: 2026-04-19
Status: confirmed
Context: "Smart dealer" was initially unclear. Clarified via research that
Blackjack dealers have fixed rules — no decision space.
Decision: Dealer's "intelligence" is a separate **dialogue layer**, not a
change to card rules. Implemented as a Python HTTP service (`dealer-ai`) that
serves one-line quips per game event. Personas + bilingual (zh/en).
Affects: `dealer-ai`, `ue-plugin`, `ui-web`, `ui-3d`

## D-004 — v1 scope: UE primary, web front-ends frozen
Date: 2026-04-21
Status: confirmed
Context: User chose to focus v1 on the UE 3D casino experience rather than
continue splitting effort across web + UE.
Decision: UE plugin is the primary v1 deliverable. `ui-web` and `ui-3d` are
**frozen** at current state — only bug fixes, no new features. TS engine
continues to be developed as the **reference implementation** (authoritative
for rules; C++ port ships inside UE). dealer-ai service is cross-platform
Python, called over HTTP by UE.
Affects: all modules; `ui-web`/`ui-3d` enter frozen state

## D-005 — TS engine stays in sync, C++ follows
Date: 2026-04-21
Status: confirmed
Context: TS engine is smaller and easier to iterate; C++ is the production
target for UE. Risk of divergence.
Decision: Every new engine mechanic (multi-seat, heat, morale, NPC AI) is
implemented and tested in TS first, then ported to C++. Conformance
vector corpus keeps them in lock-step. TS tests are the spec.
Affects: `engine`, `ue-plugin/BlackjackCore`

## D-006 — dealer-ai is an independent process, not embedded in UE
Date: 2026-04-21
Status: confirmed
Context: Options were (a) independent Python service, (b) compile llama.cpp
into UE. CosyVoice is Python-native and doesn't fit (b).
Decision: Keep `dealer-ai` as a separate Windows-compatible HTTP service.
UE plugin calls it over 127.0.0.1 (or LAN). Service is shipped alongside
the game with a launcher that starts it as a background process.
Affects: `dealer-ai`, `ue-plugin`

## D-007 — Multi-seat table, 1 dealer + N players, 6 seats default
Date: 2026-04-21
Status: confirmed
Context: Product is casino-realistic, not heads-up.
Decision: Engine models `seats[]` where one seat is human and others can be
NPC or empty. Default table: 6 seats. Standard casino turn order (seat 1 to
seat N, then dealer). Shared shoe, shared dealer.
Affects: `engine`, `ai-npc`, `ue-plugin`

## D-008 — NPC AI: rule-based, not reinforcement learning
Date: 2026-04-21
Status: confirmed
Context: RL toolkits (RLCard / OpenSpiel) converge to basic strategy anyway,
add heavy deps, are harder to audit.
Decision: NPC AI = Basic Strategy lookup + Hi-Lo counter + 7 personality
overlays (optimal / counter / amateur / chaser / superstitious / ritualistic
/ risk_averse). Hand-coded tables from Wizard of Odds + standard references.
No PyTorch / TensorFlow.
Affects: `ai-npc`, `ue-plugin`

## D-009 — Psychological layer: heat, morale, bluff, tells
Date: 2026-04-21
Status: confirmed
Context: Inspired by user request + research on casino films (Casino, 21,
Rounders, Croupier, God of Gamblers).
Decision: v1 implements (a) heat meter (pit-boss surveillance), (b) morale
bar (player mental state), (c) gesture system for player bluffs, (d) per-NPC
tell system, (e) dealer-state evolution (fresh/seasoned/compromised), (f)
dealer pressure dialogue. See module AGENT.md files for each.
Affects: `engine`, `ai-npc`, `dealer-ai`, `ue-plugin`

## D-010 — Deferred backlog (v1.5+)
Date: 2026-04-21
Status: confirmed
Context: To keep v1 shippable.
Decision: F1–F9 (team play, rigged dealer, comps, focus, compulsion, VIP,
mentor, sister games, tournaments) deferred to v1.5+. Kept in
`docs/FUTURE_FEATURES.md`.
Affects: scope only

## D-011 — Target deploy: Windows, gamer-class hardware
Date: 2026-04-21
Status: confirmed
Context: Commercial product target.
Decision: Server-side (dealer-ai) runs on Windows headless. UE plugin runs
in UE 5.3+ game on Windows. Minimum: i5/Ryzen 5 class CPU, 16 GB RAM, NVIDIA
GPU with 6+ GB VRAM (for CosyVoice real-time). CPU-only fallback disables
TTS, keeps text quips. Linux is dev-only; must stay portable.
Affects: `dealer-ai`, `ue-plugin`

## D-012 — PM / subagent division of labor
Date: 2026-04-21
Status: confirmed
Context: Main conversation was getting overloaded doing both planning and
coding. Context window at risk.
Decision: PM (primary conversation) handles product direction, interface
design, coordination, user communication, integration. All **feature code**
work is dispatched to subagents via the Agent tool. Subagents operate per
their module's `AGENT.md`. Escalations go through PM, not direct to user.
Affects: working method; no module-level impact

## D-013 — Coordination directory is the memory
Date: 2026-04-21
Status: confirmed
Context: Crash / context-loss recovery must be reliable.
Decision: `coordination/` is committed to git and is the single entry point
for any fresh conversation (`RESUME.md`). State is on disk, not in chat
history. Sessions logged to `coordination/sessions/`.
Affects: working method

## D-014 — Bilingual zh/en, chosen at session start
Date: 2026-04-21
Status: confirmed
Context: Primary market + international option.
Decision: User picks zh or en at session start, not mid-session. All
dealer-ai prompts/fallbacks ship both. Voice (CosyVoice) also dual.
Affects: `dealer-ai`, `ue-plugin`

## D-015 — Windows installer ships AI service + model + UE game as one package
Date: 2026-04-21
Status: confirmed
Context: Commercial product, end-user can't run scripts.
Decision: Final installer bundles (1) `dealer-ai.exe` built via PyInstaller,
(2) a default Qwen GGUF model, (3) the UE game binary, (4) the
`game-server.exe` (added in D-016). Installer registers both services under
Windows Service. UE launcher ensures both services are up before connecting.
Model download can be deferred to first run for installer size.
Affects: `dealer-ai`, `game-server`, `ue-plugin`, installer (future)

## D-016 — Networked multi-player is a v1 feature via authoritative server
Date: 2026-04-21
Status: confirmed
Context: User clarified that 1–6 real players can join a table from
separate terminals. Local single-player and multi-player must share the
same code path — single-player just connects the UE client to a local
loopback server (127.0.0.1).
Decision: Introduce a new module `packages/game-server` — the authoritative
game server. UE client is always a network client, even in single-player
(where it connects to a locally-spawned server subprocess). The server
owns shoe/dealer/state; clients send intent; server validates + broadcasts.
Supersedes the prior implicit "single-player only" v1 assumption from
earlier in planning.
Affects: all modules; UE plugin's `BlackjackCore` becomes optional (see D-020)

## D-017 — A session may claim 1..6 seats on a single table
Date: 2026-04-21
Status: confirmed
Context: In UE single-player, the human user drives multiple avatars; in
multi-player, a user may buy in at multiple spots (standard casino play).
Decision: Each client session (= one UE terminal connection) can claim any
number of available seats, 1 through 6. Seat ownership is enforced by the
server: actions must come from the owning session. Unclaimed seats are
NPC or empty per table config.
Affects: `game-server`, `ue-plugin`, `engine` (Seat type gains `ownerSessionId`)

## D-018 — Protocol: WebSocket + JSON, versioned frames
Date: 2026-04-21
Status: confirmed
Context: Alternatives were msgpack (unneeded, bandwidth not a concern for
card games) and UE built-in networking (not cross-language friendly since
server is Node.js).
Decision: WebSocket transport, JSON message envelope, every frame carries
`{v: 1, type, ...}` so a v2 can be introduced without breaking v1 clients.
Schemas defined in `packages/game-server/src/protocol/` and mirrored in
the UE client.
Affects: `game-server`, `ue-plugin`

## D-019 — Identity is guest-nickname only in v1
Date: 2026-04-21
Status: confirmed
Context: Full account system is a v2 concern. v1 must let someone play
in under a minute.
Decision: No login. Client sends a `displayName` on HELLO; server assigns
a `sessionId` (UUID). No persistence between launches. Bankroll is
per-session — resets on disconnect.
Affects: `game-server`, `ue-plugin`

## D-020 — Game server language is Node.js + TypeScript
Date: 2026-04-21
Status: confirmed
Context: Alternatives were Python (would require porting TS engine to
Python), Go, C#. User briefly considered Python because of AI ecosystem.
Decision: Node.js. Rationale: (1) reuses `@blackjack/engine` directly with
zero code porting; (2) AI needs live in `dealer-ai` Python service and
future AI services, not in game-server — standard microservice pattern;
(3) Node's event loop suits low-frequency WebSocket game state; (4) mature
packaging via `pkg` / `bun --compile` to Windows exe. Not chosen: Python
(engine port cost, GIL), Go (engine port cost), C++ (unrelated to AI,
high friction). See also D-005: TS engine stays authoritative.
Affects: `game-server`

## D-021 — UE `BlackjackCore` C++ port demoted to v2 offline mode
Date: 2026-04-21
Status: confirmed (supersedes parts of D-005)
Context: Once the authoritative server exists, the UE client doesn't need
its own rules engine — it just renders server state. The C++ port's only
remaining value is an offline-without-server mode.
Decision: `packages/ue-plugin/Source/BlackjackCore/` stays in the repo but
is **frozen** alongside ui-web/ui-3d. No new features. Conformance tests
still run. The UE client in v1 connects to `game-server` via WebSocket,
using a new `UBlackjackNetClient` that replaces direct engine use. This
saves one full C++ refactor cycle. If a "pure offline" mode is desired in
v2, the port is re-unfrozen.
Affects: `ue-plugin/BlackjackCore` (frozen), `ue-plugin/BlackjackUE` (new net client)

## D-022 — Reconnect policy
Date: 2026-04-21
Status: confirmed
Context: Network hiccups are normal; we need a rule.
Decision: A disconnected session retains its seat ownership for 45 seconds.
If the session reconnects within the grace window (same sessionId), it
resumes its seats. If not, seats revert to the table's configured fallback
(NPC or empty). In-flight decisions on that seat (e.g. mid-action) are
cancelled and replayed if the seat becomes NPC — NPC makes a new decision
using ai-npc; if empty, round continues with that seat inactive.
Affects: `game-server`
