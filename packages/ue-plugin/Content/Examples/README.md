# Examples

This directory holds **example Blueprint assets** that ship with the plugin:

- `BP_BlackjackTable` — Blueprint child of `ABlackjackTableActor`. Pre-configured with
  placeholder cube meshes and default `CardActorClass` / `ChipStackClass` assignments.
- `BP_BlackjackCard` — Blueprint child of `ABlackjackCardActor` with a placeholder
  card mesh. Replace the `CardMesh` asset reference with your own mesh.
- `BP_BlackjackDealer` — Blueprint child of `ABlackjackDealerCharacter` using the
  default UE mannequin + the mannequin's built-in `Idle` montage assigned to all four
  animation slots as a placeholder. Swap the skeletal mesh + montages for your dealer.
- `BP_BlackjackChipStack` — Blueprint child of `ABlackjackChipStackActor`.
- `L_CasinoDemo` — Example Level with the above actors placed, spotlight, floor, skybox.
  Level Blueprint wires `OnBigWin` to a Sequencer camera push-in as a reference example.
- `DemoLevelSequence_BigWin` — Sequencer asset referenced by the Level Blueprint.

## Why these aren't committed as `.uasset` files

`.uasset` files are binary and engine-version-specific. They are generated the first
time you open the `SampleProject/BlackjackSample.uproject` in your UE editor: on first
launch UE sees this `Examples/` folder is empty of cooked assets and creates the
example BPs for you by running the `BlackjackSample` module's startup code.

If you want to hand-build them (recommended for inspection), follow the guide in
`../../README.md` → "Designer workflow" — it takes ~5 minutes.

## Hand-build recipe (alternative to opening the SampleProject)

1. In Content Browser, right-click → Blueprint Class → search `BlackjackTableActor` → create `BP_BlackjackTable` here.
2. Open it, set `CardActorClass = BP_BlackjackCard`, `ChipStackClass = BP_BlackjackChipStack`.
3. Similarly create BP children for `ABlackjackCardActor`, `ABlackjackChipStackActor`, `ABlackjackDealerCharacter`.
4. Make a Level. Drop `BP_BlackjackTable` at the origin. Drop `BP_BlackjackDealer` behind it.
5. Select the table, set `Dealer` to your dealer instance.
6. Add a SpotLight pointing at the table. Save. Hit Play.
