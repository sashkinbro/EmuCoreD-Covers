# Nine Nintendo platform pipeline

`multiplatform_covers.py` exhaustively pages IGDB by increasing ID, round robin across
Nintendo DS (20), Nintendo 3DS/New Nintendo 3DS (37/137), GameCube (21), Wii (5), GBA (24), GB (33),
GBC (22), NES (18) and SNES (19). IDs were checked against the live IGDB platforms
endpoint. The separate original combined index and assets remain available.

Use Python 3.11+ and install Pillow and numpy (verified with Pillow 12.3.0 and
numpy 2.5.3). The two adjacent DS/3DS renderer
modules are copies of the application's existing approved renderers. The seven
additional systems reuse their perspective geometry, shadows, light/dark cases,
and transparent 840x1080 WebP output. Their spine labels identify the correct
platform. Their physical front quad follows the original scan aspect ratio,
including square and landscape boxes. They center the physical box on a fixed
transparent output canvas, preserve the complete original front image, and do
not synthesize missing artwork or claim authentic retail spines.

From this repository:

```powershell
python tools/multiplatform_covers.py catalog --config C:/path/to/private/config.py
python tools/multiplatform_covers.py assets --workers 16 --render-workers 6
python tools/multiplatform_covers.py assets --download-only --workers 16
python tools/multiplatform_covers.py validate
python tools/multiplatform_covers.py contact-sheet
python tools/multiplatform_selftest.py
```

The private configuration must export `TWITCH_CLIENT_ID` and
`TWITCH_CLIENT_SECRET`. It must stay outside this repository. Tokens remain in
memory; requests and catalogs do not contain authentication headers. Catalog
refresh is explicit (`catalog --refresh`). A normal catalog run resumes at the
last saved IGDB ID. Individual downloads/renders use atomic replacement and resume
from verified existing files. Asset progress is printed every 100 downloads and
25 renders; every 250 renders also checkpoints `reports/progress.json`.
Each original has a `.source.json` checkpoint binding URL and SHA256; each render
has a `.render.json` checkpoint binding its source digest, platform, title, theme
and renderer version. A changed IGDB image or renderer invalidates the cache.

`assets --limit 24` creates a review batch per platform and includes any exact
local seed matches outside the batch. Omitting the limit processes the complete
catalog; use `--seeds E:/nINtENDO` to choose a local seed directory. Seed files
are neither uploaded nor included. Their filenames, sizes and identity tags are
recorded in the report. Treat this report as local inspection evidence, not a
verified ROM identification database.

## Manifest contract

- `catalogs/<platform>.json`: original IGDB game/cover/alias/version metadata,
  platform membership and platform release dates/regions, final query, retrieval
  time, cursor and pagination completion status. This is a platform catalog,
  including homebrew, compilations and Virtual Console releases where IGDB lists
  the queried platform; it is not a curated physical-retail-only catalog.
- `platforms/<platform>/index.json`: only complete verified flat/light/dark sets.
  `games` is keyed by IGDB ID and includes paths, SHA256 for all three artifacts,
  original IGDB 1080p URL/image ID, release/version metadata and renderer identity.
- `titles`: only unambiguous normalized canonical titles and aliases. Normalization
  preserves `+` as `plus` so ROM hacks do not collide with original titles.
- `title_candidates`: arrays retain every ambiguous mapping for explicit client
  resolution. Each index is isolated by exact IGDB platform membership. No global
  title fallback is safe across these nine systems.
- `serials`: verified existing DS/3DS index mappings only, classified by existing
  product-code conventions and constrained to platform membership. New consoles
  currently have no ingested verified serial/hash database. Their title matches
  must not be presented as serial/hash-verified identity.
- `reports/<platform>-missing.json`: separate `no_igdb_cover` and `assets_pending`
  reasons, including every catalog record without a complete set.
- `reports/summary.json`: catalog, source availability and complete asset counts.

Region and revision tags in seed filenames remain verbatim. IGDB's global cover
does not identify an artwork region: `artwork_region` is explicitly
`unspecified_by_igdb`. Release regions do not prove that a scan belongs to that
region. Different platform releases may legitimately share an IGDB ID and cover;
their paths and mappings are still platform scoped. Original downloaded bytes
are preserved without enlargement or alteration; `t_1080p` cannot increase the
resolution of a low-resolution IGDB original.

Validation decodes every referenced artifact, checks SHA256, dimensions and alpha,
provenance against original catalog metadata, exact platform membership, complete
pagination and safe ambiguity handling. It also checks that light and dark
renders differ. The generated contact sheet provides visual review of all nine
systems. Existing DS/3DS rendered assets are reused only when their corresponding
flat bytes exactly match the newly fetched IGDB source and the WebP is valid.
