# Desert tileset (tracked)

The world floor and every prop are served from the master atlas kept in
`tileset_desert.png`:

- **Floors** are baked as 64×64 tile cells by
  `scripts/slice_environment.py` (`plain_*.png` / `brush_*.png`).
- **Props** have no PNG slices at all — `core/iso_engine.py`
  (`_PROP_WINDOWS`, `make_atlas_prop`) crops them from the atlas at load
  time into the engine's 256×256 sprite canvases.
- `path_tiles.png` is a derived path-stone bake (tinted + extruded from
  `plain_1.png`; see the slicer).

> Desert tileset by Amstrad (desert-tileset.png) — **CC-BY-SA 3.0**
> <https://opengameart.org/content/desert-tileset>
>
> "Desert tileset made by modifying the Grasslands tileset from Flare" —
> Flare game assets are CC-BY-SA 3.0:
> <https://opengameart.org/content/grassland-tileset>

Re-bake floors/portal circles/path stone after editing the atlas:

    python scripts/slice_environment.py

Prop changes go through `_PROP_WINDOWS` in `core/iso_engine.py` (window
rectangle + NEAREST upscale factor).

- `ofdn_backup/` — candidate tiles from an unknown author; kept local only.
