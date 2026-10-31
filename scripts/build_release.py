"""
Build the one-file executable with PyInstaller and zip it for distribution.

Run per target OS (PyInstaller cannot cross-compile):
    python scripts/build_release.py                 # includes everything on disk
    python scripts/build_release.py --no-private-packs
        # temporarily removes the non-redistributable pack content from the
        # build; use this for zips you intend to UPLOAD (itch.io, GitHub, ...)

Output: dist/BoundToRot-<version>-<os>-<arch>.zip
The zip holds the renamed executable plus LICENSE / README / credits.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRIVATE_PACKS = (
    'vfx',
)
PRIVATE_FILES = (
    '+ Update.txt', 'Animation Index.txt', 'Asset Index.txt', 'Licence.txt',
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
        if not d.is_dir():
            continue
        if any(p.is_file() and p.name.lower() != 'readme.md'
               for p in d.rglob('*')):
            found.append(name)
    found += [n for n in PRIVATE_FILES if (ROOT / 'assets' / n).exists()]
    return found


def hide_packs(packs) -> list:
    """Move pack folders/files outside assets/ so PyInstaller can't see
    them; returns [(hidden, original)] pairs."""
    stash = ROOT / '.private_packs_tmp'
    stash.mkdir(exist_ok=True)
    moved = []
    for name in packs:
        src = ROOT / 'assets' / name
        tmp = stash / name
        if tmp.exists():
            shutil.rmtree(tmp)
        src.rename(tmp)
        moved.append((tmp, src))
    for name in PRIVATE_FILES:
        src = ROOT / 'assets' / name
        if src.exists():
            tmp = stash / name
            src.rename(tmp)
            moved.append((tmp, src))
    return moved


def restore_packs(moved) -> None:
    stash = ROOT / '.private_packs_tmp'
    for tmp, src in moved:
        if tmp.exists():
            if src.exists():                  # paranoia: never clobber
                print(f'[build] ERROR: {src} reappeared while {tmp} hidden')
                continue
            src.parent.mkdir(parents=True, exist_ok=True)
            tmp.rename(src)
    if moved and stash.exists() and not any(stash.iterdir()):
        stash.rmdir()


def main() -> None:
    ap = argparse.ArgumentParser(description='Build and zip Bound To Rot.')
    ap.add_argument('--no-private-packs', action='store_true',
                    help='exclude the non-redistributable asset pack content '
                         '(use for zips you will upload)')
    args = ap.parse_args()

    version = project_version()
    tag = f'{os_tag()}-{platform.machine().lower()}'
    exe_src = ROOT / 'dist' / ('main.exe' if os.name == 'nt' else 'main')

    packs = has_private_packs()
    moved = []
    if args.no_private_packs and packs:
        print(f'[build] excluding non-redistributable packs: {", ".join(packs)}')
        moved = hide_packs(packs)
    try:
        print(f'[build] PyInstaller main.spec (BoundToRot {version}, {tag})')
        subprocess.run(
            [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
             str(ROOT / 'main.spec')],
            cwd=ROOT, check=True)
    finally:
        restore_packs(moved)

    if not exe_src.exists():
        sys.exit(f'[build] expected executable missing: {exe_src}')

    if args.no_private_packs:
        print('[build] private packs excluded: this zip is safe to publish.')
    elif packs:
        print('[build] WARNING: this build bundles NON-REDISTRIBUTABLE '
              'pack content:')
        print('[build] WARNING:  ' + ', '.join(packs))
        print('[build] WARNING: do not publish this zip; '
              'rebuild with --no-private-packs for releases.')

    exe_name = 'BoundToRot.exe' if os.name == 'nt' else 'BoundToRot'
    stage = ROOT / 'dist' / f'BoundToRot-{version}-{tag}'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy2(exe_src, stage / exe_name)
    for extra in ('LICENSE', 'README.md'):
        if (ROOT / extra).exists():
            shutil.copy2(ROOT / extra, stage / extra)
    if (ROOT / 'credits').is_dir():
        shutil.copytree(ROOT / 'credits', stage / 'credits')

    zip_base = ROOT / 'dist' / f'BoundToRot-{version}-{tag}'
    shutil.make_archive(str(zip_base), 'zip',
                        root_dir=stage.parent, base_dir=stage.name)
    shutil.rmtree(stage)

    zip_path = Path(str(zip_base) + '.zip')
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f'[build] done: {zip_path} ({size_mb:.1f} MB)')


if __name__ == '__main__':
    main()
