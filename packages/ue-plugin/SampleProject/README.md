# Blackjack SampleProject (pure C++)

A fully working Blackjack demo built on top of the `Blackjack` UE plugin. The
project is **100% C++**: no `.uasset` files, no Blueprint GameMode, no UMG
widgets. Everything — the GameMode, PlayerController, Pawn, HUD, and the entire
EnhancedInput mapping — is constructed in code at `BeginPlay`. You can clone,
generate, build, and run it without ever opening the UE editor UI.

Validated against **Unreal Engine 5.6**.

## Prereqs

- Unreal Engine **5.6** installed (default path `C:\Program Files\Epic Games\UE_5.6`).
  Set `UE_ROOT` as an environment variable if your install lives elsewhere.
- Visual Studio 2022 (Game Development with C++ workload) or JetBrains Rider.
- The matching `@blackjack/game-server` and (optional) `dealer-ai` services
  running locally. Default connection target: `ws://127.0.0.1:7878`.

## Quick start

From this directory:

```bat
GenerateProjectFiles.bat
BuildEditor.bat
RunEditor.bat
```

- **GenerateProjectFiles.bat** — invokes `UnrealBuildTool -projectfiles` to
  produce the VS solution.
- **BuildEditor.bat** — calls Epic's `Build.bat` with
  `BlackjackSampleEditor Win64 Development` and waits for the mutex so it plays
  nicely with a concurrent IDE build.
- **RunEditor.bat** — launches `UnrealEditor.exe BlackjackSample.uproject`.

### PowerShell alternative

If you prefer PowerShell, each `.bat` maps cleanly to a one-liner:

```powershell
& "$env:UE_ROOT\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe" `
  -projectfiles -project="$PSScriptRoot\BlackjackSample.uproject" -game -engine -progress

& "$env:UE_ROOT\Engine\Build\BatchFiles\Build.bat" `
  BlackjackSampleEditor Win64 Development `
  -project="$PSScriptRoot\BlackjackSample.uproject" -WaitMutex -FromMsBuild

Start-Process "$env:UE_ROOT\Engine\Binaries\Win64\UnrealEditor.exe" `
  -ArgumentList "$PSScriptRoot\BlackjackSample.uproject"
```

## Runtime behaviour

- The editor opens the engine built-in `/Engine/Maps/Templates/OpenWorld` map
  (there are no sample `.umap` assets shipped on disk — this keeps the project
  binary-clean).
- Pressing **Play-In-Editor** (or launching the Game target) starts
  `ABlackjackSampleGameMode`, which in `BeginPlay`:
  1. Spawns `ABlackjackNetTableActor` at world origin.
  2. Spawns `ABlackjackDealerCharacter` behind the felt.
  3. Spawns `ABlackjackPitBossActor` off to the side.
  4. Spawns `ABlackjackDecisionTimerActor`.
  5. Spawns 6 `ABlackjackChipStackActor` instances in a hex and wires them into
     `SeatBankrollStacks` + `SeatBetTransforms`.
  6. Resolves the `UBlackjackNetClient` subsystem and calls `Connect(host, port,
     displayName)`.
- The pawn is `ABlackjackSamplePawn` — a static `ADefaultPawn` subclass with a
  fixed overhead `UCameraComponent`.
- The HUD (`ABlackjackSampleHUD`) paints connection state, phase, active seat,
  local bankroll, and the last dealer quip via `Canvas->DrawText`.
- The player controller (`ABlackjackSamplePlayerController`) constructs a
  runtime `UInputMappingContext` + 15 `UInputAction`s via `NewObject<>`, pushes
  the IMC onto the local player's `UEnhancedInputLocalPlayerSubsystem`, and
  dispatches every key press to the corresponding `UBlackjackNetClient::Send*`.

### Command-line overrides

```bat
RunEditor.bat -game -bjhost=10.0.0.5 -bjport=7878 -bjname=Alice
```

Recognised args (parsed by the GameMode):

| Arg           | Default       | Meaning                        |
|---------------|---------------|--------------------------------|
| `-bjhost=`    | `127.0.0.1`   | game-server host               |
| `-bjport=`    | `7878`        | game-server WebSocket port     |
| `-bjname=`    | `TestPlayer`  | display name advertised via HELLO |

## Keybindings

| Key   | Action                               |
|-------|--------------------------------------|
| `1`   | Quick bet 5 on your seat             |
| `2`   | Quick bet 25                         |
| `3`   | Quick bet 100                        |
| `H`   | Hit                                  |
| `S`   | Stand                                |
| `D`   | Double                               |
| `P`   | Split                                |
| `R`   | Surrender                            |
| `N`   | New round                            |
| `C`   | Gesture: Confident                   |
| `X`   | Gesture: Nervous                     |
| `O`   | Gesture: PokerFace                   |
| `T`   | Gesture: Taunt                       |
| `G`   | Gesture: Sigh                        |
| `V`   | Gesture: Celebrate                   |

All bindings live in
`BlackjackSamplePlayerController::BuildInputMappings()`. A C++ subclass can
override them by rebuilding `InputMapping` before `ActivateInputMapping()`.

## Packaging

```bat
BuildGame.bat
RunGame.bat
```

`BuildGame.bat` drives `RunUAT BuildCookRun` for a Win64 Shipping archive under
`Saved/StagedBuilds/`. `RunGame.bat` launches the packaged executable.

## Troubleshooting

1. **"UnrealBuildTool.exe not found" / "Build.bat not found"** — your UE
   install is not at the default path. Set `UE_ROOT` to your 5.6 install root
   (e.g. `set UE_ROOT=D:\UE_5.6`) and rerun.
2. **"Plugin 'Blackjack' failed to load because module … could not be found"**
   — regenerate project files (`GenerateProjectFiles.bat`) and rebuild the
   editor target. The plugin lives one directory up via `AdditionalPluginDirectories`.
3. **Client shows "Connection: Disconnected"** — the sample can't reach the
   game-server. Start `@blackjack/game-server` locally (`npm run dev --workspace=@blackjack/game-server`)
   and confirm the port with `-bjport=`.
4. **EnhancedInput keys do nothing** — verify `DefaultPlayerInputClass` in
   `Config/DefaultEngine.ini` points at `EnhancedPlayerInput`. If you added
   a custom PlayerController in a child plugin, ensure it also chains through
   `Super::SetupInputComponent()` so the IMC gets bound.

## Asset policy

No `.uasset` files are tracked in git. The project intentionally ships zero
content — everything you see at runtime is either constructed from C++ or
pulled from the engine's built-in asset pool.
