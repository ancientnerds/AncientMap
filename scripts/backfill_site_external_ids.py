"""Key the curated set by enwiki title + Wikidata QID (prospector stage 0).

    ssh ancientnerds "docker exec -i ancient_nerds_api python -u -" < scripts/backfill_site_external_ids.py
    ... with --all to re-resolve sites that already have rows.

~93 Wikipedia API calls for 4,632 titles, zero LLM.
"""

import argparse

from pipeline.database import get_session
from pipeline.lyra.prospector.external_ids import refresh_site_external_ids, refresh_token_df

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--all", action="store_true", help="re-resolve sites that already have ids")
args = parser.parse_args()

with get_session() as session:
    counts = refresh_site_external_ids(session, only_missing=not args.all)
    tokens = refresh_token_df(session)
    print(f"site_external_ids: {counts}")
    print(f"site_name_token_df rows upserted: {tokens}")
