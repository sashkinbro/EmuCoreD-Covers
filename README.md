# EmuCoreD-Covers

IGDB game artwork repository for **EmuCoreD**, covering Nintendo DS/DSi,
Nintendo 3DS/New Nintendo 3DS, GameCube, Wii, Game Boy Advance, Game Boy,
Game Boy Color, NES/Family Computer and SNES/Super Famicom.

## Platform-scoped catalog

The nine separate `platforms/<platform>/index.json` manifests provide source
IGDB images plus transparent light and dark 3D cases. The platform keys are
`nds`, `n3ds`, `gamecube`, `wii`, `gba`, `gb`, `gbc`, `nes` and `snes`.
Only complete flat/light/dark sets appear in these ready manifests.
`catalogs/` preserves the full source metadata, including records without IGDB
cover artwork. Current coverage and missing-data reasons are in
`reports/summary.json` and the per-platform missing reports.

Every artifact has a SHA256 digest and original IGDB image provenance. Artwork
region remains unspecified where IGDB does not identify it. Platform titles and
ambiguous candidates stay isolated; an identical title on two consoles does not
imply the same release. Square and landscape scans retain their proportions in
the new case profiles. No replacement artwork is generated for missing scans.

| Console family | Catalog records | Complete flat/light/dark sets |
| --- | ---: | ---: |
| Nintendo DS / DSi | 4,093 | 3,956 |
| Nintendo 3DS / New Nintendo 3DS | 2,265 | 2,193 |
| GameCube | 932 | 905 |
| Wii | 3,189 | 3,098 |
| Game Boy Advance | 2,316 | 2,091 |
| Game Boy | 1,503 | 1,449 |
| Game Boy Color | 1,471 | 1,390 |
| NES / Family Computer | 2,824 | 2,528 |
| SNES / Super Famicom | 3,096 | 2,922 |
| **Total** | **21,689** | **20,532** |

All 20,532 records with an IGDB cover image have complete sets. The remaining
1,157 records have no cover image in IGDB's global cover field. Catalogs retain
those records with explicit missing-data reports. Platform-family mappings
preserve all 13 actual IGDB platform IDs, release regions and version identities.

See [pipeline instructions](tools/README.md) for checkpointing, reproducible
acquisition/rendering, metadata limitations and validation. The original combined
index and `covers/` assets below remain available at their existing paths.

## Original combined catalog
- **1080p High-Resolution 2D Covers (`covers/`)**: 6067 covers at maximum IGDB fidelity
- **Authentic 3D Box Cases (`covers/3d/`)**: Authentic 3D cases for Nintendo 3DS (translucent white with 3DS red badge) and Nintendo DS (dual-screen emblem & NTR styling)
- **Dark Edition 3D Cases (`covers/3d/dark/`)**: Sleek graphite and charcoal dark edition 3D cases for Dark and OLED themes
- **Complete Mappings (`index.json` & `index.min.json`)**: 23976 serial and Title ID mappings + 5977 normalized titles

## Original combined structure
- Direct Flat Cover: `covers/<igdb_id>.jpg`
- Direct 3D Cover (Light): `covers/3d/<igdb_id>.webp`
- Direct 3D Cover (Dark): `covers/3d/dark/<igdb_id>.webp`
- Index: `index.json` maps `serials` (e.g. `0004000000030800`, `CTRPAQEE`, `NTR-A2DE`, `A2DE`) and `titles` to game artwork.
