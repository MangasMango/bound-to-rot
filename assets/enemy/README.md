# Enemy sprite sets

16-direction isometric frames rendered with the
[3d-to-isometric](https://github.com/MangasMango/3d-to-isometric) tool.
These sets are tracked with the repository.

- `skeleton/` - rendered from the skeleton character of the
  [Flare game](https://github.com/flareteam/flare-game) -
  **CC BY-SA 3.0** (attribution required, see its `CREDITS.txt`).
  Flare ships the rigged 3D source (`.blend`); the same pipeline
  re-rendered its original skinning/animation conventions into our
  16-direction frame format.
- `slime/`, `zombie_licker/` - made in-house, no third-party source.

Frame naming: `{name}_{dir}_{DIR_ANGLE[dir]}_{frame}.png`
(`core.iso_engine.IsoSprite.load`).
