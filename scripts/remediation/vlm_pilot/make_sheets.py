"""Contact sheets for the 200-image measurement set - four PNGs, one per tier.

Run:
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe \
        scripts/remediation/vlm_pilot/make_sheets.py

Out:
    output/remediation/vlm_pilot/contact_sheet_<tier>.png   50 tiles, 5 x 10
    output/remediation/vlm_pilot/tiles/<tier>/<label>.jpg   the same tile alone,
                                                            for zooming in
    output/remediation/vlm_pilot/SHEETS.json                tile index -> image_id

Each tile is one image from `SAMPLE.jsonl`, letterboxed (never cropped, so
nothing is hidden) and labelled with `<Tier><index 00-49>` on the left of its
caption bar and `#<image_id>` on the right. **No filename, title or site name is
printed on a tile** - the label is supposed to be a judgement of the picture, and
the Commons file title gives the answer away ("... - From a Drawing - MET
DP146175"). The metadata sits in `SHEETS.json` and `SAMPLE.jsonl` instead.

Pillow 11.3.0 is present in `./.venv`; if it were not, this script says so and
exits non-zero rather than writing a partial sheet.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import OUT_DIR, read_jsonl  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit(f"Pillow is not installed in this interpreter: {exc}") from exc

COLS = 5
ROWS = 10
TILE = 320
CAPTION = 40
MARGIN = 10
GUTTER = 8
HEADER = 52
BACKDROP = (24, 24, 28)
TILE_BG = (58, 58, 64)
INK = (245, 245, 240)
DIM = (170, 170, 178)
ERROR_INK = (255, 90, 90)

FONT_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def main() -> int:
    rows = list(read_jsonl(OUT_DIR / "SAMPLE.jsonl"))
    if len(rows) != 200:
        raise SystemExit(f"REFUSING: SAMPLE.jsonl has {len(rows)} records, expected 200")

    font_index = load_font(30)
    font_id = load_font(19)
    font_header = load_font(24)

    sheets: dict[str, object] = {}
    sheet_paths: list[Path] = []
    for tier in ("A", "B", "C", "D"):
        tier_rows = [r for r in rows if r["tier"] == tier]
        if len(tier_rows) != 50:
            raise SystemExit(f"REFUSING: tier {tier} has {len(tier_rows)} records")
        tier_rows.sort(key=lambda r: r["sheet_index"])
        if [r["sheet_index"] for r in tier_rows] != list(range(50)):
            raise SystemExit(f"REFUSING: tier {tier} sheet indices are not 0..49")

        width = MARGIN * 2 + COLS * TILE + (COLS - 1) * GUTTER
        height = HEADER + MARGIN * 2 + ROWS * (TILE + CAPTION) + (ROWS - 1) * GUTTER
        sheet = Image.new("RGB", (width, height), BACKDROP)
        draw = ImageDraw.Draw(sheet)
        label = tier_rows[0]["tier_label"]
        draw.text(
            (MARGIN, 14),
            f"Tier {tier} ({label}) - 50 images - SAMPLE.jsonl seed 20260921 - "
            f"tile <index> = SHEETS.json .tiers.{tier}.tiles[<index>]",
            fill=INK,
            font=font_header,
        )

        tiles: list[dict] = []
        for position, row in enumerate(tier_rows):
            col, line = position % COLS, position // COLS
            x = MARGIN + col * (TILE + GUTTER)
            y = HEADER + MARGIN + line * (TILE + CAPTION + GUTTER)
            draw.rectangle([x, y, x + TILE - 1, y + TILE + CAPTION - 1], fill=TILE_BG)

            tile_label = f"{tier}{position:02d}"
            record: dict = {
                "index": position,
                "label": tile_label,
                "image_id": row["image_id"],
                "site_id": row["site_id"],
                "site_name": row["site_name"],
                "tier_reason": row["tier_reason"],
                "filename": row["filename"],
                "local_file_path": row["local_file_path"],
            }
            thumb = None
            try:
                with Image.open(row["local_file_path"]) as source:
                    converted = source.convert("RGB")
                    converted.thumbnail((TILE - 8, TILE - 8))
                    thumb = converted.copy()
            except Exception as exc:  # a tile that cannot be drawn must be visible, not silent
                record["error"] = f"{type(exc).__name__}: {exc}"
            if thumb is not None:
                sheet.paste(
                    thumb,
                    (x + (TILE - thumb.width) // 2, y + (TILE - thumb.height) // 2),
                )
                (OUT_DIR / "tiles" / tier).mkdir(parents=True, exist_ok=True)
                thumb.save(OUT_DIR / "tiles" / tier / f"{tile_label}.jpg", "JPEG", quality=88)
            else:
                draw.text((x + 12, y + 12), "IMAGE\nERROR", fill=ERROR_INK, font=font_index)

            draw.text((x + 8, y + TILE + 4), tile_label, fill=INK, font=font_index)
            draw.text(
                (x + TILE - 8, y + TILE + 10),
                f"#{row['image_id']}",
                fill=DIM,
                font=font_id,
                anchor="ra",
            )
            tiles.append(record)

        out = OUT_DIR / f"contact_sheet_{tier}.png"
        sheet.save(out, "PNG", optimize=True)
        sheet_paths.append(out)
        sheets[tier] = {
            "sheet": str(out.resolve()),
            "tier_label": label,
            "tiles": tiles,
            "tile_size_px": TILE,
            "grid": f"{COLS}x{ROWS}",
        }
        print(f"wrote {out.resolve()}  ({width}x{height}px)")

    payload = {
        "sheet_index_meaning": (
            "tile index 0..49 in reading order (left to right, top to bottom) within one "
            "tier's sheet; identical to SAMPLE.jsonl's sheet_index for that tier"
        ),
        "seed": 20260921,
        "sample_file": str((OUT_DIR / "SAMPLE.jsonl").resolve()),
        "sample_path": "output/remediation/vlm_pilot/SAMPLE.jsonl",
        "note": (
            "tiles carry no filename/title/site name on purpose - the label is meant to be a "
            "judgement of the picture; those fields are here and in SAMPLE.jsonl"
        ),
        "tiers": sheets,
    }
    out = OUT_DIR / "SHEETS.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    print(f"wrote {out.resolve()}")

    # A blank label sheet, so the by-eye labels come back keyed the same way the
    # VLM answers are (image_id), and no index can be transposed by hand.
    template_path = OUT_DIR / "LABELS.template.jsonl"
    with open(template_path, "w", encoding="utf-8", newline="\n") as handle:
        for row in sorted(rows, key=lambda r: (r["tier"], r["sheet_index"])):
            handle.write(
                json.dumps(
                    {
                        "sheet_accession": f"{row['tier']}{row['sheet_index']:02d}",
                        "tier": row["tier"],
                        "sheet_index": row["sheet_index"],
                        "image_id": row["image_id"],
                        "human_kind": None,
                        "note": (
                            "fill human_kind with one of site_photo | artifact | map_or_document | "
                            "painting_or_artwork | people | other, or leave null if the picture "
                            "cannot be judged; join to VLM.jsonl on image_id"
                        ),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    print(f"wrote {template_path.resolve()}")
    errors = [
        (tier, t["label"], t["error"])
        for tier, block in sheets.items()
        for t in block["tiles"]  # type: ignore[index]
        if t.get("error")
    ]
    print(f"tiles that failed to render: {len(errors)}")
    for item in errors:
        print(f"  {item}")
    for path in sheet_paths:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
