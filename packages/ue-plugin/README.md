# Blackjack UE Plugin

Native Unreal Engine 5.x plugin that embeds a full blackjack rules engine (C++ port of
the TypeScript `@blackjack/engine`) and exposes it to Blueprints as actions, events,
actors, and characters — **for use inside a real 3D casino scene** with dealer
characters, card meshes, chip stacks, cinematics, and storyline hooks. **Not** a web
overlay.

## What's in the box

| Module | Purpose |
|---|---|
| `BlackjackCore` | Pure C++ rules engine. No UE deps beyond `Core`. Mirrors the TS engine 1:1; validated via `conformance/` JSON vectors. |
| `BlackjackUE`   | UE-facing: `UBlackjackGameComponent`, `ABlackjackTableActor`, `ABlackjackCardActor`, `ABlackjackChipStackActor`, `ABlackjackDealerCharacter`, `UBlackjackBlueprintLibrary`. All Blueprint-friendly. |

## Install

1. Copy this folder into your UE project's `Plugins/Blackjack/`.
2. Regenerate project files (right-click `.uproject` → Generate Visual Studio project files).
3. Build from your IDE. The plugin auto-loads.
4. In the editor: **Edit → Plugins → Gameplay → Blackjack → Enabled**.

## Blueprint API (summary)

### `UBlackjackGameComponent` — add to any Actor, this is the brain

**Actions (BlueprintCallable):**
- `PlaceBet(Amount, SideBets)`
- `Hit() / Stand() / Double() / Split() / Surrender()`
- `Insure(Amount) / DeclineInsurance()`
- `NewRound()`
- `SetRuleSetAsset(RuleSet)` — Vegas / Spanish21 / Pontoon / SuperFun21

**Events (BlueprintAssignable — wire these to your Sequencer, AnimMontages, dialogue, quest system):**
- `OnPhaseChanged(NewPhase)`
- `OnCardDealt(Target, HandIndex, Card, bFaceDown)`
- `OnHoleCardRevealed(Card)`
- `OnPlayerAction(Action, HandIndex)`
- `OnHandBust(HandIndex)` / `OnNaturalBlackjack(HandIndex)`
- `OnBetSettled(HandIndex, Outcome, Payout)` / `OnRoundOver(Results)`
- `OnBankrollChanged(NewBankroll, Delta)` / `OnBigWin(Amount)` / `OnBankrupt()`
- `OnSideBetWin(Kind, Payout, Label)`

## Designer workflow (wiring a 3D casino scene)

1. Build your casino Level normally — felt table mesh, crowd NPCs, ambient props, lights.
2. Drop `ABlackjackTableActor` (or a Blueprint child of it) at the bet circle.
3. Place your dealer character — either use `ABlackjackDealerCharacter` or a BP child.
   Assign the DealCard / FlipHole / PayPlayer / CollectChips animation montages in the
   Details panel.
4. In the table actor, set `CardActorClass` to your card BP (with a real card mesh) and
   `ChipStackClass` to your chip stack BP.
5. `ABlackjackTableActor` already binds engine events → spawns card actors, plays dealer
   montages, updates chip stacks. You get a working 3D blackjack table.
6. For **storyline integration**, open the GameComponent's Details → Events → and bind:
   - `OnBigWin` → Level Sequencer (e.g., camera push-in + crowd cheer VFX)
   - `OnNaturalBlackjack` → dialogue line via your Dialogue plugin + Niagara burst
   - `OnBankrupt` → trigger a quest state change, call Execute on a BTTask, etc.

## Asset policy (v1)

All shipped meshes are **placeholder primitives** (UE engine `Cube` / `Cylinder`). The
plugin's visual actors expose their mesh/material properties as `EditAnywhere`, so
replacing them with real casino art in a Blueprint child requires zero code changes.

## Sample project

`SampleProject/BlackjackSample.uproject` — open in UE 5.3+, hit Generate Project Files,
build, and Play-in-Editor. The demo `GameMode` spawns an `ABlackjackTableActor` + a
placeholder dealer character on a flat template level. You'll see card cubes flying from
the deck slot to bet circles and chips restacking as bets settle.

## Conformance tests

`Source/BlackjackCore/Tests/BlackjackConformanceSpec.cpp` runs under UE Automation. It
loads the JSON corpus emitted by `packages/conformance` (TS engine) and asserts that
the C++ engine produces identical outcomes. Run from the editor:

    Tools → Session Frontend → Automation → search "Blackjack.Conformance.ReplayVectors"

This is the contract that keeps the C++ port and TS engine in lock-step. If you change
one engine, regenerate the vectors (`npm run conformance:export`) and the UE tests must
still pass.

## Performance / deployment notes

- Fully native: no network, no IPC, no Node sidecar.
- Works in packaged PC / console builds (no platform-specific deps).
- `Seed = 0` uses UTC ticks for a random shoe. Non-zero seeds give deterministic shoes
  — ideal for replays, save/load, and netcode.
