"""Google Search Console reporting for ancientnerds.com.

Pulls search analytics, sitemap status, and URL inspection data via the
Search Console REST API using the gsc-reader service account.

Setup (done 2026-07-30):
- GCP project: ancientnerds-seo
- Service account: gsc-reader@ancientnerds-seo.iam.gserviceaccount.com
- Key file: secrets/gsc-key.json (gitignored)
- The service account must be added as a user (Full) on the property
  in Search Console -> Settings -> Users and permissions.

Usage:
    python scripts/gsc_report.py summary            # totals + top queries/pages (28 days)
    python scripts/gsc_report.py queries --days 90  # top search queries
    python scripts/gsc_report.py pages              # top pages by clicks
    python scripts/gsc_report.py countries          # clicks by country
    python scripts/gsc_report.py sitemaps           # submitted sitemaps + status
    python scripts/gsc_report.py inspect <url>      # index status of one URL
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY_FILE = Path(__file__).resolve().parent.parent / "secrets" / "gsc-key.json"
SCOPES = ["https://www.googleapis.com/auth/webmasters"]
API = "https://searchconsole.googleapis.com/webmasters/v3"
INSPECT_API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


def get_session() -> AuthorizedSession:
    creds = service_account.Credentials.from_service_account_file(str(KEY_FILE), scopes=SCOPES)
    return AuthorizedSession(creds)


def detect_property(session: AuthorizedSession) -> str:
    """Return the siteUrl of the ancientnerds property the service account can access."""
    resp = session.get(f"{API}/sites")
    resp.raise_for_status()
    entries = resp.json().get("siteEntry", [])
    for entry in entries:
        if "ancientnerds" in entry["siteUrl"]:
            return entry["siteUrl"]
    raise SystemExit(
        "Service account has no access to an ancientnerds property.\n"
        "Add gsc-reader@ancientnerds-seo.iam.gserviceaccount.com in "
        "Search Console -> Settings -> Users and permissions.\n"
        f"Accessible properties: {[e['siteUrl'] for e in entries] or 'none'}"
    )


def query_analytics(session, site_url, dimensions, days, limit):
    end = date.today()
    start = end - timedelta(days=days)
    resp = session.post(
        f"{API}/sites/{site_url.replace('/', '%2F').replace(':', '%3A')}/searchAnalytics/query",
        json={
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": dimensions,
            "rowLimit": limit,
        },
    )
    resp.raise_for_status()
    return resp.json().get("rows", [])


def print_rows(rows, label):
    if not rows:
        print(f"  (no {label} data)")
        return
    print(f"  {'Clicks':>7} {'Impr.':>8} {'CTR':>6} {'Pos.':>5}  {label}")
    for row in rows:
        key = " | ".join(row["keys"])
        print(
            f"  {row['clicks']:>7.0f} {row['impressions']:>8.0f} "
            f"{row['ctr'] * 100:>5.1f}% {row['position']:>5.1f}  {key}"
        )


def cmd_summary(session, site_url, args):
    totals = query_analytics(session, site_url, [], args.days, 1)
    print(f"Property: {site_url}  (last {args.days} days)\n")
    if totals:
        t = totals[0]
        print(
            f"Totals: {t['clicks']:.0f} clicks, {t['impressions']:.0f} impressions, "
            f"CTR {t['ctr'] * 100:.1f}%, avg position {t['position']:.1f}\n"
        )
    print("Top queries:")
    print_rows(query_analytics(session, site_url, ["query"], args.days, args.limit), "query")
    print("\nTop pages:")
    print_rows(query_analytics(session, site_url, ["page"], args.days, args.limit), "page")


def cmd_dimension(dimension):
    def run(session, site_url, args):
        print(f"Property: {site_url}  (last {args.days} days)\n")
        print_rows(
            query_analytics(session, site_url, [dimension], args.days, args.limit), dimension
        )

    return run


def cmd_sitemaps(session, site_url, args):
    encoded = site_url.replace("/", "%2F").replace(":", "%3A")
    resp = session.get(f"{API}/sites/{encoded}/sitemaps")
    resp.raise_for_status()
    for sm in resp.json().get("sitemap", []):
        print(json.dumps(sm, indent=2))


def cmd_resubmit(session, site_url, args):
    """Re-submit sitemap.xml so Google downloads it again (picks up new URLs)."""
    encoded = site_url.replace("/", "%2F").replace(":", "%3A")
    sitemap = "https%3A%2F%2Fancientnerds.com%2Fsitemap.xml"
    resp = session.put(f"{API}/sites/{encoded}/sitemaps/{sitemap}")
    resp.raise_for_status()
    print(f"Sitemap re-submitted for {site_url} (HTTP {resp.status_code})")


def cmd_inspect(session, site_url, args):
    resp = session.post(
        INSPECT_API,
        json={"inspectionUrl": args.url, "siteUrl": site_url},
    )
    resp.raise_for_status()
    print(json.dumps(resp.json()["inspectionResult"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["summary", "queries", "pages", "countries", "sitemaps", "resubmit", "inspect"],
    )
    parser.add_argument("url", nargs="?", help="URL for the inspect command")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    if args.command == "inspect" and not args.url:
        parser.error("inspect requires a URL argument")

    session = get_session()
    site_url = detect_property(session)

    handlers = {
        "summary": cmd_summary,
        "queries": cmd_dimension("query"),
        "pages": cmd_dimension("page"),
        "countries": cmd_dimension("country"),
        "sitemaps": cmd_sitemaps,
        "resubmit": cmd_resubmit,
        "inspect": cmd_inspect,
    }
    handlers[args.command](session, site_url, args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
