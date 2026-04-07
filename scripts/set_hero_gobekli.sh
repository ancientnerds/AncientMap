#!/bin/bash
# One-shot: Set Göbekli Tepe hero image via API container
# Copies an existing gallery image as hero.webp and updates the DB

SITE_ID="d953e9b3-de33-4c7d-9357-bbc5d94d2a16"
SID_SHORT="d953e9b3"
IMG_DIR="/var/www/ancientnerds/public/data/images/wiki/$SID_SHORT"

# Pick the Pillar image as hero (one of the best photos)
SRC="$IMG_DIR/Göbekli_Tepe_Pillar.webp"
DST="$IMG_DIR/hero.webp"

if [ ! -f "$SRC" ]; then
  echo "Source image not found: $SRC"
  # Try another image
  SRC=$(ls "$IMG_DIR"/*.webp 2>/dev/null | grep -v hero | head -1)
  if [ -z "$SRC" ]; then
    echo "No images found in $IMG_DIR"
    exit 1
  fi
  echo "Using fallback: $SRC"
fi

cp "$SRC" "$DST"
chmod a+r "$DST"
echo "Copied hero image: $DST"

TIMESTAMP=$(date +%s)

docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c "
  UPDATE wiki_images SET is_hero = false WHERE site_id = '$SITE_ID' AND is_hero = true;
  UPDATE unified_sites SET thumbnail_url = '/data/images/wiki/$SID_SHORT/hero.webp?v=$TIMESTAMP' WHERE id = '$SITE_ID';
"

echo "DB updated. Hero set for Göbekli Tepe."
