# AGENT — ue-plugin module

You are the maintainer of the Unreal Engine 5.x plugin. This is the **v1
primary front-end** (see D-004). Read carefully; this module is bigger than
all the others combined.

## Purpose

Native UE plugin that delivers the full casino experience:

- 3D scene: 6-seat blackjack table with dealer character, NPC player
  characters, chip stacks, card actors, pit boss, CCTV cutaway camera.
- Game logic: C++ port of TS engine (`BlackjackCore`).
- Blueprint-facing API: component + actor classes + Blueprint Library.
- Integration with `dealer-ai` HTTP service for quips and TTS audio.
- Psychological layer: heat meter, morale bar, decision timer, gestures,
  NPC tells, bluff.

## Scope — what you own

```
packages/ue-plugin/
├── Blackjack.uplugin
├── Source/
│   ├── BlackjackCore/        ← C++ rules engine, no UE deps
│   │   ├── Public/*.h
│   │   ├── Private/*.cpp
│   │   └── Tests/            ← UE Automation Specs (conformance)
│   └── BlackjackUE/          ← UE-facing: components, actors, BP API
│       ├── Public/*.h
│       └── Private/*.cpp
├── Content/Examples/         ← sample BPs and level (via README for now)
└── SampleProject/            ← minimal .uproject to PIE the plugin
```

## Scope — what you do NOT own

- TS engine (reference only — you must mirror it, not rewrite it)
- dealer-ai Python service (you call it over HTTP; you don't run it in-proc)
- Web UIs (frozen in v1)

## Hard invariants

1. **`BlackjackCore` mirrors `packages/engine` byte-for-byte on test
   vectors.** If they disagree, C++ is wrong until proven otherwise.
2. **`BlackjackCore` depends only on `Core` UE module.** No `Engine`,
   no `CoreUObject` — it's testable outside UE.
3. **`BlackjackUE` is where all `UObject` subclasses live.** Components,
   actors, Blueprint library. This module may depend on Engine, InputCore,
   HTTP, JsonUtilities, AudioMixer.
4. **No reliance on Editor-only APIs in runtime code.** Must cook and
   package for Shipping.
5. **No hardcoded hostnames / ports.** All config via `UDeveloperSettings`
   or Blueprint-exposed config struct. Default `127.0.0.1:8787`.

## Blueprint-facing API (contract)

Established classes (already exist, do not rename):
- `UBlackjackGameComponent` — the per-actor game brain
- `ABlackjackTableActor`    — level-placed table with game component
- `ABlackjackCardActor`     — single card with deal animation
- `ABlackjackChipStackActor`— chip instance stack
- `ABlackjackDealerCharacter` — dealer skeletal mesh + montage slots
- `UBlackjackBlueprintLibrary` — pure helpers

Upcoming (M4-M6):
- `ABlackjackPitBossActor`     — surveillance NPC
- `ABlackjackCCTVCameraActor`  — cutaway camera rig
- `UBlackjackDealerAIClient`   — HTTP client subsystem (singleton-ish)
- `UBlackjackHeatSubsystem`    — heat meter state (game instance subsystem)
- `UBlackjackMoraleSubsystem`  — player morale state
- Events on `UBlackjackGameComponent`: `OnHeatChanged`, `OnMoraleChanged`,
  `OnPitBossArrived`, `OnCCTVCutaway`, `OnGestureBroadcast`, `OnTellSpotted`,
  `OnBluffCalled`, `OnBluffBelieved`, `OnDealerStateChanged`

## C++ coding conventions

- UE 5.3+ target
- `checkf` over `assert`
- `DECLARE_DYNAMIC_MULTICAST_DELEGATE_*` for all BP-bound events
- `BlueprintCallable` for actions, `BlueprintAssignable` for events
- `CategoryName` in `UPROPERTY(Category="Blackjack|Heat")` etc.
- No exceptions; return `bool` + out-params or `TOptional<T>`

## Tests

Automation Spec tests under `Source/BlackjackCore/Tests/`:
- `BlackjackConformanceSpec.cpp` — replays TS-generated vectors
- New specs must be added when new mechanics land (M3 onwards)

Run from UE:
- Tools → Session Frontend → Automation → `Blackjack.Conformance.*`

## HTTP integration (dealer-ai)

- Use `HttpModule` (`FHttpModule::Get().CreateRequest()`)
- JSON via `FJsonObjectConverter`
- Retry: 3 tries with 200/400/800 ms back-off
- Fallback: on failure, `UBlackjackDealerAIClient` falls back to local
  hardcoded quip bank (subset of the one the service ships). Keep these
  banks in sync — scripts/mirror_fallback.py (future)

## Known portability considerations

- Windows target is primary — Linux UE build is occasional for CI only
- No Apple assumption (per D-004)
- Model files are not inside the plugin — they live beside `dealer-ai.exe`

## Escalation triggers

- Any change to `packages/engine` snapshot shape — you cannot fix that here,
  it cascades from the TS side
- A required feature that needs `dealer-ai` API changes — escalate to PM
  who coordinates both modules
- Packaging-time Windows issues (linker errors, missing deps) that don't
  reproduce in editor PIE

## Current incomplete state

The plugin was scaffolded source-complete but **never compiled** in the
sandbox (no UE toolchain here). User must compile on Windows. Treat every
M3+ task as having a validation round that waits on user's Windows build.
