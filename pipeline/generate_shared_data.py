"""Generate shared JSON files from Python constants for frontend consumption.

Run:  python pipeline/generate_shared_data.py
      python pipeline/generate_shared_data.py --verify   (CI mode: fail if stale)

Outputs:
  ancient-nerds-map/src/data/empires.generated.json
  ancient-nerds-map/src/data/game-constants.generated.json
"""

import importlib.util
import json
import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.historical_boundaries.empire_metadata import EMPIRE_METADATA  # noqa: E402


def _load_constants():
    """Load api.cardgame.constants without triggering api/__init__.py."""
    spec = importlib.util.spec_from_file_location(
        "api.cardgame.constants",
        PROJECT_ROOT / "api" / "cardgame" / "constants.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_constants = _load_constants()

OUT_DIR = PROJECT_ROOT / "ancient-nerds-map" / "src" / "data"


def _build_empires() -> list[dict]:
    """Build empire list from EMPIRE_METADATA."""
    return [
        {
            "id": eid,
            "name": meta["name"],
            "region": meta["region"],
            "color": meta["color"],
        }
        for eid, meta in EMPIRE_METADATA.items()
    ]


def _build_game_constants() -> dict:
    """Build game constants from Python source."""
    display_names: dict[str, str] = _constants.EMPIRE_DISPLAY_NAMES
    star_levels = {
        str(k): v["duplicates_needed"] for k, v in _constants.STAR_LEVELS.items()
    }

    pack_prices = {
        name: {"cost": p["cost"], "cards": p["cards"]}
        for name, p in _constants.PACK_PRICES.items()
    }

    trade_routes = [
        {
            "name": name,
            "empireA": display_names[a],
            "empireB": display_names[b],
            "goods": goods,
        }
        for name, a, b, goods in _constants.TRADE_ROUTES
    ]

    return {
        "starLevels": star_levels,
        "maxStarLevel": _constants.MAX_STAR_LEVEL,
        "packPrices": pack_prices,
        "tradeRoutes": trade_routes,
    }


def _serialize(data: object) -> str:
    """JSON-serialize with consistent formatting (2-space indent, trailing newline)."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def generate() -> dict[Path, str]:
    """Return {filepath: content} for all generated files."""
    return {
        OUT_DIR / "empires.generated.json": _serialize(_build_empires()),
        OUT_DIR / "game-constants.generated.json": _serialize(_build_game_constants()),
    }


def write_all() -> None:
    """Generate and write all JSON files."""
    for path, content in generate().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"  wrote {path.relative_to(PROJECT_ROOT)}")


def verify() -> bool:
    """Check that existing files match what would be generated. Returns True if up to date."""
    ok = True
    for path, expected in generate().items():
        if not path.exists():
            print(f"  MISSING: {path.relative_to(PROJECT_ROOT)}")
            ok = False
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            print(f"  STALE: {path.relative_to(PROJECT_ROOT)}")
            ok = False
    return ok


if __name__ == "__main__":
    if "--verify" in sys.argv:
        print("Verifying shared data is up to date...")
        if verify():
            print("All shared data files are up to date.")
        else:
            print(
                "\nShared data is out of date! Run:\n"
                "  python pipeline/generate_shared_data.py\n"
                "and commit the updated JSON files."
            )
            sys.exit(1)
    else:
        print("Generating shared data...")
        write_all()
        print("Done.")
