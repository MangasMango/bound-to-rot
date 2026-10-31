![Logo](assets/logo/github-logo.jpg)

*A Diablo 2-style isometric action RPG, written in Python.*

[![CI](https://img.shields.io/github/actions/workflow/status/MangasMango/bound-to-rot/ci.yml?branch=main&label=CI)](https://github.com/MangasMango/bound-to-rot/actions)
[![License: GPL v3](https://img.shields.io/github/license/MangasMango/bound-to-rot)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Steam](https://img.shields.io/badge/Steam-Store-1B2838?logo=steam&logoColor=white)](https://store.steampowered.com/app/4840980/Bound_to_Rot/)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?logo=discord&logoColor=white)](https://discord.com/invite/s2rgHuctdc)
[![itch.io Assets](https://img.shields.io/badge/itch.io-Assets-FA5C5C?logo=itch.io&logoColor=white)](https://itch.io/c/8322662/boundtorot)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/MangasMango?logo=githubsponsors&logoColor=white&label=Sponsor&color=ea4aaa)](https://github.com/sponsors/MangasMango)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/mangasmango)

_[Contributing](CONTRIBUTING.md)_  

_Started May 10, 2026. Open-sourced October 14, 2026._

## Contributing

See [CONTRIBUTING](CONTRIBUTING.md) for general code style, AI and PR guidelines.

If you'd like to report a bug or suggest a feature, open an [issue](https://github.com/MangasMango/bound-to-rot/issues). Keep your own agent notes, prompts and plans in `.ai/`; it is gitignored, so each contributor's notes stay local.

## Gameplay

- **Anima** | an endless isometric descent. Depth drives everything: monster level, item level and reward quality.
- **The Pulse** | your mobile light anchor. Leave its light radius and darkness starts eating you alive. Clear a wave and the Pulse opens the **chart**: pick your next checkpoint, claim a 1-of-3 relic boon.
- **Vessels** | Pyrrhian (knight) — the only vessel for now. Myronian (warrior) and Theran (fighter) are work in progress.
- **Permadeath** | dying in the Anima deletes the character. Only your account-wide best depth survives.
- **Items & Tarot** | gear drops unidentified and is revealed with tarot cards, which double as crafting currency (upgrade, force mythic, reroll). Gems socketed into **Q / W / E / R** grant abilities; a **T** flask gives one charge per wave.

### Controls

| Key | Action |
|-----|--------|
| Right Click (press/hold) | Move |
| Left Click | Attack enemy / interact / ground loot / click the Pulse |
| `Q` `W` `E` `R` | Cast socketed gem abilities |
| `T` | Drink flask (1 charge per wave) |
| `I` | Toggle inventory |
| `C` | Character stats panel |
| `Tab` | Delve chart / minimap overlay (in Anima) |
| `Escape` | Pause |
| `` ` `` | Dev console (type `help` for commands) |

## Building

If you'd rather compile on your own, follow these instructions.
First, make sure you have [Python 3.12+](https://www.python.org/downloads/) installed; **older versions will not work.** Open a terminal in the project directory, install the dependencies with `uv sync` (or `pip install .`), then run the following commands.

### Windows

_Running:_ `python main.py`  
_Tests:_ `python -m pytest tests/ -q`  
_Building:_ `pyinstaller main.spec`

### Linux/Mac OS

_Running:_ `python3 main.py`  
_Tests:_ `python3 -m pytest tests/ -q`  
_Building:_ `pyinstaller main.spec`

### Assets

Game assets live in `assets/` and **not all of them are in this repository**. The `boss`, `enemy` and `none-playable character` folders (plus the `playable character` pack folder) come from a third-party pack that forbids redistribution; obtain the pack yourself and copy the files into those folders before running the game. The whole world — floor, props and portal circles — is tracked with the repository: it renders from the desert-tileset atlas in `assets/environment/` (props are cropped from the atlas at load).

The assets are collected on [itch.io](https://itch.io/c/8322662/boundtorot). If you can't find something, or you have questions about a licence, contact me on [Discord](https://discord.com/invite/s2rgHuctdc) or by [email](mailto:mangasmangostudios@gmail.com).

#### Credits

The **code** is licensed under the GPL (see [License](#license)). **Game assets are not** — they keep their original licences:

| Assets | Source & author | Licence |
|--------|-----------------|---------|
| Currency cards — `assets/cards/` | [Pixel Poker Cards](https://aspecsgaming.itch.io/mini-pixel-playing-cards) by Aspecs Gaming | CC0 1.0 |
| UI font — `assets/fonts/` | [Sancreek](https://fonts.google.com/specimen/Sancreek) by Vernon Adams | SIL OFL 1.1 |
| World tileset — `assets/environment/` | [Desert Tileset](https://opengameart.org/content/desert-tileset) by Amstrad, a modification of the [Flare grassland tileset](https://opengameart.org/content/grassland-tileset) | CC BY-SA 3.0 |
| Inventory/bank panels & orbs — `assets/ui/` | [RPG Inventory](https://opengameart.org/content/rpg-inventory), [Health Orb 1.1](https://opengameart.org/content/health-orb-11) by itsmars | CC0 1.0 |
| UI icons — `assets/ui-icons/` | [1-bit Pixel Icons](https://nikoichu.itch.io/pixel-icons) by Nikoichu | CC0 1.0 |
| Ability gem icons — `assets/ability-icons/` | [Icons - Dark Magic](https://opengameart.org/content/icons-dark-magic) by Cethiel | CC0 1.0 |
| Menu GUI kit — `assets/gui/` | [RPG GUI Construction Kit v1.0](https://opengameart.org/content/rpg-gui-construction-kit-v10) by Lamoot | CC BY 3.0 |
| Sound effects — `assets/ui-sfx/`, `assets/ingame-sfx/` | [Kenney](https://kenney.nl) (UI Audio, Interface Sounds, RPG Audio, Impact Sounds, Footsteps) | CC0 1.0 |
| Music — `assets/ost/` | [Spaghetti Western Guitar Stab](https://opengameart.org/content/spaghetti-western-guitar-stab) by SpringySpringo (CC BY 3.0); [Spaghetti Western Theme (Orchestral)](https://opengameart.org/content/spaghetti-western-theme-orchestral) by linxiaoma (CC BY 4.0); [Lobo Loco](https://freemusicarchive.org/music/Lobo_Loco/tunnel-games) | CC BY 4.0 |
| Knight vessel | rendered from the Hero Clint gunslinger model (Sketchfab) with [3d-to-isometric](https://github.com/MangasMango/3d-to-isometric) | CC BY 4.0 |
| Skeleton enemy | rendered from the [Flare game](https://github.com/flareteam/flare-game) skeleton character | CC BY-SA 3.0 |
| Icon, logo, pulse, item sprites, VFX shaders | made in-house | — |

Slash/sparkle/flame/glow VFX are generated by code (GLSL shaders in `assets/shaders/`). The muzzle-flash/bullet-impact sprites (Hit-Yellow by Sinestesia & Mikodrak) stay **local only** — their licence is not confirmed yet, so they are not distributed with the repository.

The full file → track mapping lives in [`credits/SOURCES.txt`](credits/SOURCES.txt) and in the per-folder `credits.txt` / `README.md` files. **AI-generated assets are prohibited** in contributions; make new art yourself (see [Contributing](CONTRIBUTING.md)).

### Troubleshooting

#### Permission Denied

If the terminal returns `Permission denied` or `Command not found` on Mac/Linux when running `python3`, make sure Python 3.12+ is actually installed (`python3 --version`).

## Downloads

[Bound to Rot on Steam](https://store.steampowered.com/app/4840980/Bound_to_Rot/)

## Support

If you want to support development, you can sponsor me on [GitHub Sponsors](https://github.com/sponsors/MangasMango) or [buy me a coffee on Ko-fi](https://ko-fi.com/mangasmango).

## License

Source code: [GNU General Public License v3.0 or later](LICENSE).

Game assets are **not** covered by the GPL; they stay under their original licences, see [Assets](#assets) and [`credits/SOURCES.txt`](credits/SOURCES.txt).
