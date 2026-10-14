"""
Build the one-file executable with PyInstaller and zip it for distribution.

Run per target OS (PyInstaller cannot cross-compile):
    python scripts/build_release.py

Output: dist/BoundToRot-<version>-<os>-<arch>.zip
The zip holds the renamed executable plus LICENSE / README / THIRD_PARTY_ASSETS.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRIVATE_PACKS = (
    'boss', 'environment', 'enemy', 'none-playable character',
    'playable character', 'prop', 'user interface', 'vfx',
)


def project_version() -> str:
    try:
        import tomllib
    except ImportError:                       # Python < 3.11
        return '0.0.0'
    with open(ROOT / 'pyproject.toml', 'rb') as f:
        return tomllib.load(f)['project']['version']


def os_tag() -> str:
    return {'windows': 'win', 'darwin': 'macos'}.get(
        platform.system().lower(), platform.system().lower())


def has_private_packs() -> list:
    found = []
    for name in PRIVATE_PACKS:
        d = ROOT / 'assets' / name
        if d.is_dir() and any(p.is_file() and p.name.lower() != 'readme.md'
                              for p in d.rglob('*')):
            found.append(name)
    return found


def main() -> None:
    version = project_version()
    tag = f'{os_tag()}-{platform.machine().lower()}'
    exe_src = ROOT / 'dist' / ('main.exe' if os.name == 'nt' else 'main')

    print(f'[build] PyInstaller main.spec (BoundToRot {version}, {tag})')
    subprocess.run(
        [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
         str(ROOT / 'main.spec')],
        cwd=ROOT, check=True)
    if not exe_src.exists():
        sys.exit(f'[build] expected executable missing: {exe_src}')

    packs = has_private_packs()
    if packs:
        print('[build] WARNING: this build bundles NON-REDISTRIBUTABLE packs:')
        print('[build] WARNING:  ' + ', '.join(packs))
        print('[build] WARNING: do not publish this zip; use CI-built releases instead.')

    exe_name = 'BoundToRot.exe' if os.name == 'nt' else 'BoundToRot'
    stage = ROOT / 'dist' / f'BoundToRot-{version}-{tag}'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy2(exe_src, stage / exe_name)
    for extra in ('LICENSE', 'README.md', 'THIRD_PARTY_ASSETS.md'):
        if (ROOT / extra).exists():
            shutil.copy2(ROOT / extra, stage / extra)

    zip_base = ROOT / 'dist' / f'BoundToRot-{version}-{tag}'
    shutil.make_archive(str(zip_base), 'zip',
                        root_dir=stage.parent, base_dir=stage.name)
    shutil.rmtree(stage)

    zip_path = Path(str(zip_base) + '.zip')
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f'[build] done: {zip_path} ({size_mb:.1f} MB)')


if __name__ == '__main__':
    main()
