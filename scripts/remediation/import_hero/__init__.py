"""WD2/IH: the 2025 import's linked image takes the hero flag (owner decision 2026-10-05, 17:43).

`ancient_nerds_original.geojson` (2025-12-18) is the only surviving copy of the image the owner
hand linked per site: the loader wrote its `Images` property into `unified_sites.thumbnail_url`
(`pipeline/unified_loader.py:1200`), and the remediation since then replaced, demoted or removed
most of those. The owner's decision is that the import's image wins as hero, and that of the
1,980 promotions the 427 whose local file is under 1600x900 are fetched at 1600 px first.

Nothing in this package writes to production. `plan.write_chunks` emits the chunks the shared
writer (`gallery_audit.chunk_writer`) then applies, each with its journal identity, its undo
written before the write, and its own transaction.
"""
