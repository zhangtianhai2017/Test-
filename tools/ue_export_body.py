"""Export a MetaHuman body SkeletalMesh to a skinned .glb from the
command line, without opening the UE editor UI.

Invoked via:
  UnrealEditor-Cmd.exe <project>.uproject \
    -ExecutePythonScript="tools/ue_export_body.py <metahuman_path> <out_glb>"

Example:
  UnrealEditor-Cmd.exe BikiniValidator.uproject -stdout -unattended \
    -ExecutePythonScript="C:/work/2026/Claude/test-/tools/ue_export_body.py /Game/MetaHumans/NPC_swim_G_34 C:/work/2026/Claude/test-/body.glb"

The first argument is the **folder** containing the MetaHuman assets;
the script searches it recursively for the body SkeletalMesh (asset
whose name matches /body/i and which is the largest skel mesh in the
folder). The second argument is the output .glb path (absolute).
"""
import sys
import unreal


def _find_body_skel(folder: str):
    asset_lib = unreal.EditorAssetLibrary
    paths = asset_lib.list_assets(folder, recursive=True, include_folder=False)
    candidates = []
    for p in paths:
        # ListAssets returns paths like "/Game/MetaHumans/.../SK_xxx.SK_xxx"
        a = asset_lib.load_asset(p)
        if isinstance(a, unreal.SkeletalMesh):
            name = a.get_name().lower()
            if "body" in name:
                candidates.append(a)
    if not candidates:
        # fallback: any skel mesh
        for p in paths:
            a = asset_lib.load_asset(p)
            if isinstance(a, unreal.SkeletalMesh):
                candidates.append(a)
    if not candidates:
        return None
    # pick the one with most vertices (the body, not e.g. eyelashes)
    candidates.sort(key=lambda m: m.get_num_vertices(0) if hasattr(m, "get_num_vertices") else 0, reverse=True)
    return candidates[0]


def main():
    argv = sys.argv[1:]
    if len(argv) < 2:
        unreal.log_error("usage: ue_export_body.py <metahuman_folder> <out_glb_path>")
        return
    folder, out_path = argv[0], argv[1]

    skel = _find_body_skel(folder)
    if skel is None:
        unreal.log_error(f"no SkeletalMesh found under {folder}")
        return
    unreal.log(f"exporting {skel.get_path_name()} -> {out_path}")

    task = unreal.AssetExportTask()
    task.set_editor_property("object", skel)
    task.set_editor_property("filename", out_path)
    task.set_editor_property("automated", True)
    task.set_editor_property("prompt", False)
    task.set_editor_property("replace_identical", True)

    # Try glTF first (built-in glTFExporter plugin must be enabled).
    options = unreal.GLTFExportOptions()
    options.set_editor_property("export_vertex_colors", True)
    options.set_editor_property("export_vertex_skin_weights", True)
    options.set_editor_property("export_textures", True)
    task.set_editor_property("options", options)

    ok = unreal.Exporter.run_asset_export_task(task)
    if not ok:
        unreal.log_error("glTF export failed (is the 'glTF Exporter' plugin enabled?)")
        return
    unreal.log(f"wrote {out_path}")


main()
