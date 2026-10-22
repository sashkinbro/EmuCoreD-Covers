# EmuCoreD-Covers

Universal ultra-high-definition game cover repository for **EmuCoreD** (Nintendo 3DS, Nintendo DS & Nintendo DSi emulator for Android).

## Content
- **1080p High-Resolution 2D Covers (`covers/`)**: 6067 covers at maximum IGDB fidelity
- **Authentic 3D Box Cases (`covers/3d/`)**: Authentic 3D cases for Nintendo 3DS (translucent white with 3DS red badge) and Nintendo DS (dual-screen emblem & NTR styling)
- **Dark Edition 3D Cases (`covers/3d/dark/`)**: Sleek graphite and charcoal dark edition 3D cases for Dark and OLED themes
- **Complete Mappings (`index.json` & `index.min.json`)**: 23976 serial and Title ID mappings + 5977 normalized titles

## Structure
- Direct Flat Cover: `covers/<igdb_id>.jpg`
- Direct 3D Cover (Light): `covers/3d/<igdb_id>.webp`
- Direct 3D Cover (Dark): `covers/3d/dark/<igdb_id>.webp`
- Index: `index.json` maps `serials` (e.g. `0004000000030800`, `CTRPAQEE`, `NTR-A2DE`, `A2DE`) and `titles` to game artwork.
