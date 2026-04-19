# Blackjack — Headless Engine + Pluggable UIs + Native UE Plugin

A casino-style blackjack game split into a pure, headless rules engine and several
independent frontends — including a **native Unreal Engine 5 plugin** designed to be
embedded in a 3D casino scene with real dealer characters, card meshes, chip stacks,
cinematics, and storyline integration (not a web overlay).

## Packages

| Package | What it is |
|---|---|
| `packages/engine` | Pure-TypeScript rules engine. Zero DOM / Three.js / UE deps. The authoritative rules implementation. Vitest tests, deterministic RNG. |
| `packages/ui-cli` | Readline terminal UI for headless validation. |
| `packages/ui-web` | 2D HTML/CSS/Canvas UI (felt table, card flips, side-bet panel). |
| `packages/ui-3d`  | Three.js 3D UI with tweened card meshes, chip stacks, orbit camera. |
| `packages/conformance` | Exports a JSON corpus of seeded games to `vectors/`. Shared contract between the TS engine and the C++ engine. |
| `packages/ue-plugin` | UE 5.x plugin — `BlackjackCore` (C++ port of the rules) + `BlackjackUE` (Actors, Components, Blueprint API). Ships with a sample project. |

## Variants & side bets

- **Classic Vegas** (6-deck H17, BJ pays 3:2, late surrender, DAS, 3-split cap)
- **Spanish 21** (48-card deck, bonus 21s, player totals win ties over 17)
- **Pontoon** (BJ pays 2:1, no dealer peek, bonus 21s)
- **Super Fun 21** (single deck, diamond BJ, always-win player 21)
- Side bets: 21+3, Perfect Pairs, Lucky Ladies

## Running

```bash
npm install
npm test                      # engine unit tests (vitest)
npm run dev:web               # 2D UI at http://localhost:5173
npm run dev:3d                # 3D UI at http://localhost:5174
npm run cli                   # terminal UI
npm run conformance:export    # write JSON vectors for the UE port
```

## Architecture

```
                         ┌──────────────────────────────┐
                         │  packages/engine  (TypeScript)│
                         │  rules, shoe, FSM, side-bets │
                         └───────────┬──────────────────┘
            ┌────────────────────────┼────────────────────────┐
            │                        │                        │
        ui-cli                  ui-web / ui-3d          conformance/vectors/*.json
     (Node readline)            (Vite + DOM/Three)      (test corpus — shared
                                                         contract to UE port)
                                                                │
                                                                ▼
                         ┌──────────────────────────────────────┐
                         │  packages/ue-plugin  (Unreal 5.x)    │
                         │  BlackjackCore  ← same FSM in C++    │
                         │  BlackjackUE    ← Actors, Component, │
                         │                   Blueprint API      │
                         │  Conformance spec replays TS vectors │
                         └──────────────────────────────────────┘
```

## Unreal Engine integration

The UE plugin is **native**, not a web view. `BlackjackCore` is a C++ port of the TS
engine; `BlackjackUE` wraps it in a `UBlackjackGameComponent` with Blueprint-callable
actions (`Hit`/`Stand`/...) and Blueprint-assignable events (`OnCardDealt`,
`OnRoundOver`, `OnBigWin`, `OnBankrupt`, ...). Designers wire those events in Level or
Character Blueprints to real 3D things: dealer AnimMontages, card mesh spawns, chip
stack updates, Sequencer cinematics, dialogue lines, quest state changes.

See `packages/ue-plugin/README.md` for install, Blueprint API, and the designer
workflow.

## Engine↔UE parity

Both engines share the same `mulberry32` seeded RNG and identical rules. Parity is
verified by:

1. `packages/conformance` runs scripted games in the TS engine and writes
   `vectors/*.json` (each vector: ruleset, seed, full action script, expected outcomes).
2. `packages/ue-plugin/Source/BlackjackCore/Tests/BlackjackConformanceSpec.cpp` loads
   those vectors under UE Automation and replays them in C++; every final bankroll and
   per-hand outcome must match byte-for-byte.

If the TS engine changes, re-run `npm run conformance:export` and the UE test must
still pass.

## Development status

- TS engine: 43 tests, all green.
- 2D and 3D web UIs: build and run.
- UE plugin: source-complete and self-reviewed against the conformance contract.
  Compilation requires a UE 5.3+ toolchain (not available in this sandbox); open
  `packages/ue-plugin/SampleProject/BlackjackSample.uproject` locally, regenerate
  project files, and build.
