# Desert tileset (tracked)

The floor art this folder ships is sliced from the open-source desert
tileset; the master atlas is kept in `tileset_desert.png`.

> Desert tileset by Amstrad (desert-tileset.png) — **CC-BY-SA 3.0**
> <https://opengameart.org/content/desert-tileset>
>
> "Desert tileset made by modifying the Grasslands tileset from Flare" —
> Flare game assets are CC-BY-SA 3.0:
> <https://opengameart.org/content/grassland-tileset>

Re-slice after editing the atlas:

    python scripts/slice_environment.py

Files produced (do not edit by hand):

- `plain_*.png`, `brush_*.png` — normalized 256×256 floor canvases whose
  diamond matches the engine projection (`core/iso_engine.py`).
- `assets/prop/desert/**` — prop sprite canvases (see the script).
- `ofdn_backup/` — candidate tiles from an unknown author; kept local only.