# -*- mode: python ; coding: utf-8 -*-
import sys
from importlib.metadata import distributions
from pathlib import Path

sys.setrecursionlimit(5000)
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# NumPy uses internal modules that are not all visible to PyInstaller's
# normal import analysis. Collect only NumPy's submodules explicitly; do not
# recursively collect unrelated GUI/OpenGL/example packages.
hidden_imports = collect_submodules('numpy')

datas = []
datas += collect_data_files('qtawesome')
datas += collect_data_files('PySide6')

# Keep the license notices for runtime dependencies alongside the packaged app.
# Build-only tools (PyInstaller and pytest) are intentionally excluded.
_RUNTIME_DISTRIBUTIONS = {
    'pyside6',
    'pyside6-addons',
    'pyside6-essentials',
    'shiboken6',
    'pyserial',
    'pyqtgraph',
    'qtawesome',
    'qtpy',
    'numpy',
}


def collect_runtime_license_files():
    """Collect license/notice files from installed runtime dependency wheels."""
    collected = []
    seen = set()
    for dist in distributions():
        name = (dist.metadata.get('Name') or '').lower().replace('_', '-')
        if name not in _RUNTIME_DISTRIBUTIONS:
            continue
        for item in dist.files or ():
            relative = Path(str(item))
            filename = relative.name.lower()
            if not any(token in filename for token in (
                'license', 'copying', 'notice', 'copyright', 'ofl',
            )):
                continue
            source = Path(dist.locate_file(item))
            if not source.is_file():
                continue
            key = (name, source.resolve())
            if key in seen:
                continue
            seen.add(key)
            collected.append((str(source), f'third_party_licenses/{name}'))
    return collected


datas += collect_runtime_license_files()
notices_file = Path(__file__).resolve().parent / 'THIRD_PARTY_NOTICES.md'
if notices_file.is_file():
    datas.append((str(notices_file), '.'))

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
