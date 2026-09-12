#!/usr/bin/env python3
"""Fill wiki_images.width/height from the files on disk.

Warum: 49.688 der 49.693 Bildzeilen hatten keine Masse — der Massenimport
schrieb nur file_size_bytes, obwohl wiki_image_downloader.py beides kann.
Ohne Masse kann die SEO-Seite kein `<img width height>` setzen, und genau
das ist die Ursache von Layout-Shift (CLS), den Google als Ranking-Signal
misst. Neue Downloads bringen ihre Masse selbst mit; dieses Skript holt den
Altbestand nach und ist danach ein No-op.

Pillow liest bei Image.open() nur den Header — die Pixeldaten werden nie
dekodiert, deshalb kostet ein Bild ~1 ms statt ~100 ms.

Nebenbefund, den der Lauf mitnimmt: Zeilen, deren Datei fehlt, rendern auf
der Seite ein kaputtes <img>. Sie werden gezaehlt und mit --prune-missing
als is_excluded markiert, damit die Galerie sie nicht mehr anbietet.

Usage (auf dem VPS):
    docker exec ancient_nerds_api python scripts/backfill_image_dimensions.py --dry-run
    docker exec ancient_nerds_api python scripts/backfill_image_dimensions.py
    docker exec ancient_nerds_api python scripts/backfill_image_dimensions.py --prune-missing
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402
from sqlalchemy import text  # noqa: E402

from pipeline.database import SessionLocal  # noqa: E402
from pipeline.sites_html_renderer import site_id_short  # noqa: E402

DEFAULT_IMAGE_DIR = Path("/app/public/data/images/wiki")

#: Ein Commit pro Block — 49.693 Einzel-Commits wären langsam, ein einziger
#: Commit am Ende hielte die Transaktion minutenlang offen.
BATCH = 500


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGE_DIR)
    parser.add_argument("--dry-run", action="store_true", help="nichts schreiben, nur zählen")
    parser.add_argument(
        "--prune-missing",
        action="store_true",
        help="Zeilen ohne Datei auf is_excluded = true setzen",
    )
    args = parser.parse_args()

    if not args.image_dir.is_dir():
        print(f"FEHLER: {args.image_dir} existiert nicht", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT id, site_id::text AS site_id, filename
                FROM wiki_images
                WHERE width IS NULL OR height IS NULL
                ORDER BY id
            """)
        ).fetchall()
        print(f"{len(rows)} Zeilen ohne Masse", flush=True)

        updated = missing = unreadable = 0
        pending: list[dict] = []
        missing_ids: list[int] = []

        for i, row in enumerate(rows, 1):
            path = args.image_dir / site_id_short(row.site_id) / row.filename
            if not path.is_file():
                missing += 1
                missing_ids.append(row.id)
                continue
            try:
                with Image.open(path) as img:
                    width, height = img.size
            except Exception as exc:  # noqa: BLE001 — jede defekte Datei soll genannt werden
                unreadable += 1
                print(f"  unlesbar: {path} ({exc})", flush=True)
                continue

            pending.append({"id": row.id, "w": width, "h": height, "b": path.stat().st_size})
            if len(pending) >= BATCH and not args.dry_run:
                _flush(db, pending)
                updated += len(pending)
                pending.clear()
                print(f"  {i}/{len(rows)}", flush=True)

        if pending and not args.dry_run:
            _flush(db, pending)
            updated += len(pending)
        elif args.dry_run:
            updated = len(pending)

        if missing_ids and args.prune_missing and not args.dry_run:
            db.execute(
                text("UPDATE wiki_images SET is_excluded = true WHERE id = ANY(:ids)"),
                {"ids": missing_ids},
            )
            db.commit()
            print(f"{len(missing_ids)} Zeilen ohne Datei als is_excluded markiert")

        print(
            f"\nfertig: {updated} mit Massen versehen, {missing} ohne Datei, "
            f"{unreadable} unlesbar{' (DRY RUN, nichts geschrieben)' if args.dry_run else ''}"
        )
        if missing and not args.prune_missing:
            print("  --prune-missing blendet die fehlenden aus der Galerie aus")
        return 0
    finally:
        db.close()


def _flush(db, pending: list[dict]) -> None:
    """file_size_bytes kommt mit: 6 Zeilen hatten auch den nicht."""
    db.execute(
        text("""
            UPDATE wiki_images
            SET width = :w, height = :h, file_size_bytes = COALESCE(file_size_bytes, :b)
            WHERE id = :id
        """),
        pending,
    )
    db.commit()


if __name__ == "__main__":
    sys.exit(main())
