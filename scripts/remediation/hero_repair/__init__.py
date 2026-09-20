"""Phase 2 item 1 of the 2026-09 remediation: the mechanical hero repair.

The plan lives in ``docs/procedures/SITES_DB_REMEDIATION_2026-09.md`` (§6.3 "Every hero image
is broken", §Phase 2 item 1). The defect: ``HERO_WIDTH = 800`` (``api/routes/wiki_images.py:22``)
equals ``THUMB_WIDTH = 800`` (``pipeline/wiki_image_downloader.py:47``), so the image a site
serves as its hero - ``og:image``, JSON-LD ``image``, the LCP image - is no larger than a
gallery thumbnail. 3,858 curated sites carry such a hero; the site already has a 1600 px file
for most of them (``GALLERY_WIDTH = 1600``, same file), so the repair moves the ``is_hero``
flag and downloads nothing.

Package layout
--------------
``plan``    builds the offline repair plan (``PLAN.jsonl`` / ``PLAN.md`` / ``ROLLBACK.sql``)
            from the snapshot plus the census caches. No network, no database.
``apply``   turns ``PLAN.jsonl`` into one journalled transaction and (with ``--apply``) sends
            it to production the way this project reaches production: ``ssh ancientnerds``
            then ``docker exec ancient_nerds_db psql``.

Split for one reason: step 1 of an E1 write has to be reviewable before it happens, so what
*should* change is computed by a pure function of the snapshot, and the code that touches
production only ever replays that decision.
"""

__all__ = ["apply", "plan"]
