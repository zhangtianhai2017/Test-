# ue-game — UE packaging notes

The Unreal Engine game cannot be packaged from inside this `packaging/`
tree because it requires the UE Editor + Windows build tools that live on
the user's own box. This directory is therefore **instructions only** —
no scripts to run, no exes to produce.

## What the builder does

1. Open the project at `packages/ue-plugin/` in **UE 5.3+** (Windows).
2. Load the `BlackjackUE` plugin; make sure it compiles cleanly. Per
   D-021 the legacy `BlackjackCore` C++ port is frozen — don't modify.
3. **Package for Windows**: *Platforms → Windows → Package Project*. Use
   Shipping configuration unless you're hunting a bug.
4. UE writes the game tree to a path you pick. Copy the whole tree into
   `%ProgramFiles%\Blackjack\ue-game\` after running the installer (or
   ship it as a separate zip).
5. First-run UE logic (owned by `UBlackjackNetClient`) connects to
   `ws://127.0.0.1:7878/game` — which is exactly what the game-server
   service exposes. No extra UE config is needed in the single-machine
   case.

## LAN play (N players, 1 host)

- One machine acts as the host: run `packaging/installer/install.ps1`
  there. The firewall rule opened by the installer is already scoped to
  `LocalSubnet`, which is correct for LAN. The host plays via its own
  UE client against `127.0.0.1`.
- Guest machines: install the UE game only (no services), and point
  `UBlackjackNetClient::Connect(host_ip, 7878, "Nickname")` at the
  host's LAN IP (project settings → `DefaultGame.ini` override, or a
  debug console command).

## Out of scope here

- Bundling UE assets with the installer — file sizes are large and the
  layout is opinionated; we leave this to the UE builder workflow.
- Code-signing of `BlackjackGame.exe` — TODO at the installer level too.
- Pixel-streaming or cloud-hosted UE — not a v1 concern.
