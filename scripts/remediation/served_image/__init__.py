"""WD2: the served image of every curated site - checked, and replaced or cleared (O6).

Owner decision O6 (2026-09-26, "Belegt ersetzen, sonst leeren"): a served image that does not
show its site is replaced only by an image a vision check confirmed, else the site serves no
image. The stage-1 measurement of the fresh acceptance (`draw-2026-09-25b`) found 11 of 60 served
images wrong: a region or landscape view, a namesake site 45 km away, a museum object not from the
site, a portrait, a stork information panel.

``state``     the read-only read of production and which image each site serves
``commons``   the Commons API: file categories, category members, image URLs and bytes
``precheck``  the deterministic pre-check against the harvest (Wikidata P18 and P373)
``vision``    the two Opus handoff stages: the check of the served image, the replacement pick
``plan``      the decisions as planned rows for the shared image writer (`gallery_audit/chunk_writer`)
``run``       the command line

Nothing in this package writes to the database: every write is a chunk of the shared image
writer, journalled through `apply_remediation_change()`. The runbook is
`docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md`.
"""
