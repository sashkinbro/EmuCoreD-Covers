# EmuCoreD-Covers

Universal ultra-high-definition game cover repository for **EmuCoreD** (Nintendo 3DS frontend for Android).

## Content
- **1080p High-Resolution 2D Covers (`covers/`)**: 2190 covers at maximum IGDB fidelity
- **Authentic 3D Nintendo 3DS Cases (`covers/3d/`)**: 800x800 translucent white Nintendo 3DS cases with red Nintendo badge, 3DS logo, molded spine latches, Segoe UI typography, and soft transparent drop shadow
- **Dark Edition 3D Cases (`covers/3d/dark/`)**: 800x800 sleek graphite edition 3D cases for Dark and OLED themes
- **Complete Mappings (`index.json` & `index.min.json`)**: 7181 serial and Title ID mappings + 2165 normalized titles

## Structure
- Direct Flat Cover: `covers/<igdb_id>.jpg`
- Direct 3D Cover (Light): `covers/3d/<igdb_id>.webp`
- Direct 3D Cover (Dark): `covers/3d/dark/<igdb_id>.webp`
- Index: `index.json` maps `serials` (e.g. `0004000000030800`, `CTRPAQEE`, `AQEE`) and `titles` to game artwork.
