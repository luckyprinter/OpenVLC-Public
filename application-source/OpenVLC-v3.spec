# -*- mode: python ; coding: utf-8 -*-
import sys
sys.setrecursionlimit(5000)
from PyInstaller.utils.hooks import collect_data_files

# Keep PyInstaller focused on modules that are actually imported by the
# application. Broad collect_submodules() calls can import optional GUI,
# OpenGL, example, and platform-specific modules during analysis and make
# Linux builds depend on components that the application does not use.

hidden_imports = []
datas = []
datas += collect_data_files('qtawesome')
datas += collect_data_files('PySide6')

a = Analysis(
    ['run_v3.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest',
        '_pytest',
        'unittest',
        'tests',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OpenVLC-v3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OpenVLC-v3',
)
