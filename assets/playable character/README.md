# This asset folder is not distributed with this repository

The files normally found here come from a third-party asset pack whose licence
**does not allow redistribution**, so they are excluded from the public repo
(this folder's contents are gitignored; only this README is tracked).

See the **Assets** section of the repository [`README.md`](../../README.md)
for details and credits.

**To run the game:** obtain the pack yourself and copy its files for this
folder into here (matching the original file names). The game will not render
correctly without them.

## Direction swap record (2026-10-18, knight only)

The generated `knight/` set was rendered with a "camera-side" orbit that put
the FRONT view in folder N (and the back view in S) - the opposite of what
`core/iso_engine.py MOVE_DIR` needs (folder D holds the character facing
screen-direction D, seen from the fixed south-above camera). In-game this
read as walking backwards in every up-screen direction.

Fix: `3dtoIsometric\fix_directions.py` reflected the set about the E-W axis -
exact pairs **N↔S, NEE↔SEE, NE↔SE, NNE↔SSE,
NNW↔SSW, NW↔SW, NWW↔SWW** (E, W unchanged). 588 of 672 files moved; BOTH the
folder and the `_DIR_`/`_angle_` tokens in each filename were rewritten so
`IsoSprite.load` still resolves `{name}_{dir}_{DIR_ANGLE[dir]}_{frame}.png`.
`knight_original_backup/` was left untouched as the historical reference.
The generator (`3dtoIsometric\generate.py place_camera`, az = −angle) now
bakes the correct convention directly. `fighter/` and `warrior/` were NOT
touched.
