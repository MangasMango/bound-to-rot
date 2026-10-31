# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

# Local-only assets must never reach a build: the vfx sheets have an
# unconfirmed licence and the four pack text files are non-redistributable
# (see assets/vfx/credits.txt and the Assets section of README.md).
EXCLUDE_DIRS  = {'vfx'}
EXCLUDE_FILES = {'+ Update.txt', 'Animation Index.txt', 'Asset Index.txt',
                 'Licence.txt'}


def _asset_datas():
    out = []
    src_root = os.path.join(SPECPATH, 'assets')
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        rel = os.path.relpath(dirpath, src_root)
        dest = 'assets' if rel == '.' else os.path.join('assets', rel)
        for fn in sorted(filenames):
            if fn not in EXCLUDE_FILES:
                out.append((os.path.join(dirpath, fn), dest))
    return out


datas = _asset_datas()
binaries = []
hiddenimports = []
tmp_ret = collect_all('pyray')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
