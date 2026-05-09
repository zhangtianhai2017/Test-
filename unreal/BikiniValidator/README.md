# BikiniValidator (UE5.6)

A pure-C++ UE 5.6 project that loads v2 outfits from this repo's
`assets/glb/` directory onto a MetaHuman, with runtime skinning to the
MetaHuman skeleton so the outfit deforms with character animation.

## What it does

- On Play: spawns lighting, the MetaHuman, an orbit camera, and a
  scrollable outfit list (bottom-left of the viewport).
- Fetches `manifest.json` from the public branch via HTTPS.
- Click any row → downloads that `.glb`, swaps the previous outfit out,
  loads the new one as a `USkeletalMesh` sharing the MetaHuman's
  `USkeleton`, and `SetMasterPoseComponent`s it to the body so it
  follows the rig each tick.

## One-time setup

1. **Install UE 5.6.** Linux: build from source. Windows/Mac: from the
   Epic launcher.

2. **Clone this repo with submodules.**
   ```bash
   git clone --recursive <repo-url>
   # If you already cloned without --recursive:
   git submodule update --init
   ```
   This pulls `Plugins/glTFRuntime/` into `unreal/BikiniValidator/Plugins/`.

3. **Drop your MetaHuman assets.** Copy the entire `Content/MetaHuman/`
   tree from a UE project that has the matching MetaHuman exported
   into `unreal/BikiniValidator/Content/MetaHuman/`.

   See `Content/MetaHuman/README.md` for the expected layout. Anything
   you drop in here is gitignored.

4. **Set the MetaHuman path in code.** Open
   `Source/BikiniValidator/Private/BikiniValidatorGameMode.cpp` and in
   the constructor, set:
   ```cpp
   MetaHumanBPPath       = FSoftObjectPath("/Game/MetaHuman/<Name>/BP_<Name>.BP_<Name>_C");
   MetaHumanSkeletonPath = FSoftObjectPath("/Game/MetaHuman/<Name>/Body/SK_<Name>_Body_Skeleton.SK_<Name>_Body_Skeleton");
   ```
   (Or leave blank and set on the GameMode default object inside the
   editor after first compile.)

5. **Generate project files + open.**
   - Linux: `/opt/UnrealEngine/UE_5.6/GenerateProjectFiles.sh -project=$(pwd)/unreal/BikiniValidator/BikiniValidator.uproject -game -engine`
   - Windows: right-click `BikiniValidator.uproject` → *Generate Visual Studio project files*
   - Open the generated `.uproject` in the editor; it will compile
     `BikiniValidator` + `glTFRuntime`.

6. **Click Play.** Expected behaviour:
   - Orbit camera (left-mouse-drag to rotate, scroll to zoom)
   - List of 37 outfits on the left
   - Click one → bikini appears overlaying the MetaHuman
   - Drive an idle/walk animation on the MetaHuman → outfit deforms with it

## How outfits get here

The Python pipeline (top of repo) bakes outfits to skinned glTF before
this UE project ever runs:

```bash
# 1. Export the MetaHuman body as a skinned .glb (UE editor:
#    right-click Body skel mesh → Asset Actions → Export → glTF).
python3 tools/bake_body_assets.py /path/to/MetaHuman_Body.glb
#    → writes assets/glb/_body_skin.pkl

# 2. Bake every v2 seed to a skinned .glb that references the
#    MetaHuman bone names.
python3 tools/bake_v2_glb_skinned.py
#    → writes assets/glb/<seed>.glb (37 of them) + manifest.json

# 3. Push so the UE project can fetch them.
git add assets/glb && git commit -m "skinned glb assets" && git push
```

The UE project then downloads on demand via:
`https://raw.githubusercontent.com/<owner>/<repo>/<branch>/assets/glb/`
(configured via `BaseRawUrl` on the GameMode).

## Project layout

```
unreal/BikiniValidator/
├── BikiniValidator.uproject
├── Config/                       Default{Engine,Game,Input}.ini
├── Content/MetaHuman/            user-supplied .uasset (gitignored)
├── Plugins/glTFRuntime/          git submodule (rdeioris/glTFRuntime)
└── Source/BikiniValidator/
    ├── BikiniValidator.Build.cs
    ├── Public/
    │   ├── BikiniValidatorGameMode.h    play loop, downloader+loader wiring
    │   ├── OutfitDownloader.h           HTTPS manifest + .glb fetcher with cache
    │   ├── OutfitLoader.h               glTFRuntime → USkeletalMesh sharing MH skel
    │   ├── OutfitManifest.h             USTRUCTs for the JSON manifest schema
    │   ├── OutfitRowButton.h            per-row click capture
    │   ├── OrbitPawn.h                  mouse-drag orbit camera
    │   └── SimpleSelectorWidget.h       runtime-built UMG list
    └── Private/                          matching .cpp files
```

## Caveats

- **Bone-name compatibility.** The `.glb` baker writes joint names as
  exported from your MetaHuman body (whatever names appear in the FBX/
  glTF export). They MUST match the names in the MetaHuman `USkeleton`
  inside UE. If they don't (e.g. a Maya export added prefixes), edit
  `tools/bake_body_assets.py` to strip them, or use glTFRuntime's
  `SkeletonConfig.BoneRemapper`.
- **Auto-skin quality.** Proximity-based skinning gives soft seams in
  high-curvature regions (bust under-curve, inner thigh). Acceptable
  for the milestone-1 validation; future work would be heat-map or
  manual.
- **No `.umap` is committed.** The world is built procedurally in
  `GameMode::BeginPlay`; only `.uproject` + `.ini` are source-controlled,
  avoiding binary asset drift.
- **MetaHuman content licensing.** Under Epic's MetaHuman EULA you may
  not redistribute the `.uasset` files. That's why `Content/MetaHuman/`
  is gitignored and each developer must supply their own copy locally.
