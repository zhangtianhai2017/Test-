# Content/MetaHuman/

Drop your MetaHuman `.uasset` tree here. Everything in this folder
(except this README and `.gitkeep`) is gitignored.

Expected layout after dropping:

```
Content/MetaHuman/
├── README.md            (this file, tracked)
├── .gitkeep             (tracked)
├── <CharacterName>/
│   ├── BP_<CharacterName>.uasset
│   ├── Body/
│   │   ├── SK_<CharacterName>_Body.uasset       ← skeletal mesh
│   │   └── SK_<CharacterName>_Body_Skeleton.uasset  ← USkeleton
│   ├── Face/
│   ├── Hair/
│   └── ...
└── Common/              (shared MetaHuman content if separate plugin not used)
```

After dropping, edit
`Source/BikiniValidator/Private/BikiniValidatorGameMode.cpp`'s
constructor (or the GameMode default object in editor) and set:

```cpp
MetaHumanBPPath       = FSoftObjectPath("/Game/MetaHuman/<Name>/BP_<Name>.BP_<Name>_C");
MetaHumanSkeletonPath = FSoftObjectPath("/Game/MetaHuman/<Name>/Body/SK_<Name>_Body_Skeleton.SK_<Name>_Body_Skeleton");
```

The bone names in the user-supplied MetaHuman skeleton MUST match the
joint names baked into the `.glb` files by `tools/bake_v2_glb_skinned.py`
(otherwise the runtime skinning maps to no bones and the mesh stays in
T-pose). MetaHumans use the standard UE5 mannequin skeleton bone names
by default (`pelvis`, `spine_01..05`, `clavicle_l`, `upperarm_l`, …),
which is what the baker writes.
