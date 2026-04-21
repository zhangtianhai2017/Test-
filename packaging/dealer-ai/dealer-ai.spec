# PyInstaller spec for dealer-ai.exe
#
# Invocation (see build.ps1):
#     pyinstaller -y dealer-ai.spec
#
# Produces dist/dealer-ai/dealer-ai.exe (onedir layout) on Windows. We prefer
# onedir over onefile because:
#   - startup is faster (no temp-dir extraction of ~100 MB on each launch);
#   - the native llama.cpp DLLs load more reliably when they're sitting on
#     disk next to the exe;
#   - Windows Service wrapping (sc.exe / NSSM) is simpler with a real path.
#
# Paths are resolved relative to this .spec's location (packaging/dealer-ai/).
# Upstream Python package lives at ../../packages/dealer-ai/src/dealer_ai/.

# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Repo layout: packaging/dealer-ai/dealer-ai.spec -> ../../packages/dealer-ai
SPEC_DIR   = os.path.dirname(os.path.abspath(SPEC))  # noqa: F821 (injected)
REPO_ROOT  = os.path.abspath(os.path.join(SPEC_DIR, "..", ".."))
PKG_SRC    = os.path.join(REPO_ROOT, "packages", "dealer-ai", "src")
ENTRY      = os.path.join(PKG_SRC, "dealer_ai", "main.py")

# --- data files ---------------------------------------------------------
# PyInstaller's --add-data / datas=[] copies files into the bundle. Format:
# (source_path_on_builder, destination_relative_to_bundle_root).
datas = [
    (os.path.join(PKG_SRC, "dealer_ai", "personas"), "dealer_ai/personas"),
    (os.path.join(PKG_SRC, "dealer_ai", "fallback"), "dealer_ai/fallback"),
    (os.path.join(PKG_SRC, "dealer_ai", "prompts"),  "dealer_ai/prompts"),
]

# --- hidden imports -----------------------------------------------------
# PyInstaller's static analysis misses modules pulled in dynamically.
hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "pydantic",
    "pydantic.deprecated.decorator",
    "llama_cpp",
    "httpx",
]

# llama-cpp-python ships native DLLs; collect everything.
_llm_datas, _llm_bins, _llm_hidden = collect_all("llama_cpp")
datas        += _llm_datas
binaries      = list(_llm_bins)
hiddenimports += _llm_hidden

a = Analysis(
    [ENTRY],
    pathex=[PKG_SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy deps that aren't needed unless DEALER_AI_TTS_ENABLED=1 is set
        # AND the operator installed the [tts] extra. Those ship in a
        # separate bundle; the base dealer-ai.exe is LLM-only.
        "torch",
        "torchaudio",
        "modelscope",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dealer-ai",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,                # headless service: keep stdout/stderr
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,      # TODO: sign post-build
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="dealer-ai",            # -> dist/dealer-ai/
)
