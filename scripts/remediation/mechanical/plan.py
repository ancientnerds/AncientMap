"""The mechanical `unified_sites.country` repairs: what a script can settle, and why.

## The defect

The census (T05, `scripts/remediation/census/tests/t05_country_values.py`) found 70 sites whose
`country` is not the project's spelling of a country. 35 of those findings are `applicable=true`
and all 35 are `proposal=set`:

* **27 `T05/disambiguated`** - `Georgia (country)`. The parenthetical distinguishes the country
  from the US state and is part of the string every consumer sees: `/sites/georgia-country` is the
  hub slug it produces, and the narrator of a video short reads it aloud verbatim
  (`pipeline/video/shorts_tts.py` appends the country, splitting on commas only).
* **8 `T05/compound`** - `Chile, Easter Island`. Two facts in one field: the hub slug is
  `/sites/chile-easter-island`, and `extractCountry()` (`ancient-nerds-map/src/utils/searchUtils.ts`)
  takes the last comma part, so the globe's country filter lists a territory as a country. The
  *flag* is not affected: `COUNTRY_CODES` carries `'Easter Island': 'CL'` (line 289), so
  `getCountryCode()` answers `CL` for the compound - measured, and it is why the ISO code check
  below is the load-bearing one and not the flag.

The other 35 T05 findings are **not** settlable by a script (spelling splits like `USA`, vocabulary
gaps like `Northern Ireland` - a gap until 2026-09-22, when both vocabularies gained it as GB - a
value that is not a country at all) and every one of them is refused here with its reason.
`output/remediation/mechanical/SKIPPED.jsonl` holds them, so the report does not have to be
believed.

## The set, and the 27/35 decision

The candidate set is the census predicate **`applicable=true` on the T05 findings: 35 rows over 35
distinct sites** (no site carries two proposals; the count is 70 findings over 70 distinct sites,
35 of them applicable).

`output/remediation/phase3_worklist/MECHANICAL.md` lists 27 sites, because `build_worklist.py` also
applies `AND NOT phase3`. The 8 rows that filter drops carry the *same* applicable country finding
**plus** a non-applicable T01 (coordinates) or T03 (period) finding, which is a different field:
Armazi, Didnauri, Dmanisi, Kutaisi, Satsurblia Cave, Tsona Cave, Tsutskhvati Cave Natural Monument,
Easter Island.

Written on the supervisor's decision of 2026-09-21 (recorded in `PLAN.md` and `APPLIED.md`): **all
35**, because writing 27 would split one country across two hub slugs: 20 of the 27 Georgia rows
would join the 3 rows already at `/sites/georgia` while the other 7 (all of them Phase-3 sites)
stayed at `/sites/georgia-country`, and 7 of the 8 Chile rows would join the 3 already at
`/sites/chile` while `Easter Island` stayed at `/sites/chile-easter-island` - a half-migrated state
no rule produces. The 8 stay in the Phase 3 worklist and Phase 3 keeps their
T01/T03 findings; only the `country` column is written here. Ownership is per field, not per site.

## What makes a row settlable

Every value is re-derived from the sources the evidence names, not copied from the proposal. The
written value must be the **project's own canonical country string**, and it must survive six
independent checks; the first failure refuses the row (SKIPPED, with the measured reason).

1. **Reduction of the stored value** to a plain country name (`reduce_value`): a trailing
   `(country|state|nation|republic)` hint is a disambiguation note, not a name; a comma-separated
   label is reduced to the comma part that is a country. "Is a country" is measured against
   Natural Earth's feature names, because both project vocabularies carry territories as if they
   were countries: `NAME_TO_ISO` and `COUNTRY_CODES` both answer `CL` for `Easter Island`, and only
   the third party says which of the two names is an admin-0 state. Two parts that survive, a part
   that is empty, or no rule at all is a refusal - which part of a compound is the country is
   measured, not guessed.
2. **Canonical form** (`canonicalize_country_display_name`, `pipeline/utils/country_lookup.py`): the
   project's own display-name normalizer, and the written value must be its output for the reduced
   name. It is *not* enforced on `country` writes anywhere in the pipeline - measured 2026-09-21,
   `git grep -n canonicalize_country_display_name -- pipeline/ api/` finds only the definition
   (`country_lookup.py:572`); every other caller is this lane. Its docstring says connectors *should*
   route through it, which is a recommendation and not a route. So the load-bearing comparison here
   is reduction-versus-proposal: the reduced value must be a spelling the project already carries
   *and* must equal the T05 proposal. A row whose canonical form disagrees with the proposal is
   refused rather than "corrected" to a value of this module's own invention.
3. **Vocabulary 1** (`country_lookup.py`): `normalize_country(old)` and `normalize_country(new)`
   must both be the same 2-letter ISO code.
4. **Vocabulary 2** (`countryFlags.ts`): the new value must be a key of `COUNTRY_CODES` whose code
   is that ISO code, so the flag renders. The old value's code is *recorded* rather than required to
   match: both old values already resolve there (`'Georgia (Country)': 'GE'`, `'Easter Island':
   'CL'`), which is exactly why the flag is not what these two repairs fix.
5. **Geography** (Natural Earth 10m admin-0, the same cached dataset and the same 1000 m tolerance
   as T02): the row's own point must lie inside the polygon of the country the value names.
6. **Wikidata P17 -> P297** (ISO 3166-1 alpha-2), an external witness independent of both project
   vocabularies: the entity's **preferred-rank** `P17` (all of them, when Wikidata marks none as
   preferred) must include the ISO code and must not contradict it. Historical values are normal
   rank and are recorded, not refused: Kutaisi states Georgia `preferred` (since 1991-04-09) next to
   the Soviet Union (`P297 = SU`, ended the same day) and the Russian Empire. The entity is the
   `wikidata_qid` from `site_external_ids` where there is one (33 of the 35); for the two ahu without
   one it is resolved by an exact English label match **plus** a Wikidata coordinate within 1000 m of
   the row's own point, so the identity is measured and not assumed. One site states no `P17` at all
   (Kudaro), which is recorded as a gap rather than a pass - and it is not fatal either: checks 3-5
   are the mandatory ones.

A value that is already the canonical string, a row that is not `source_id = 'ancient_nerds'`, a
snapshot value the live database no longer holds, a proposal that no longer matches the row, and a
value that is not NFC or longer than the column are refusals too.

## What it does not do

* No DELETE, ever. An out-of-scope or undecidable site is flagged, never removed.
* No other column, no other table. `card_stats.civilization` repeats `country` for the card game
  (`api/cardgame/stats.py:184`, upserted by `api/cardgame/generator.py::_upsert_stats`) and is
  **not** written: the card-stats generator runs by hand or as a pipeline job, never at API boot.
  The divergence that leaves behind is a named residual, with the check SQL, in `APPLIED.md`.
* Nothing is written by this module. It emits `PLAN.jsonl`, `PLAN.md`, `SKIPPED.jsonl` and
  `ROLLBACK.sql`; `apply.py` renders and runs the transaction.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]

#: Two separate roots on purpose: the census package is `scripts/remediation/census`, so
#: `scripts/remediation` has to be importable first; `REPO` is for `pipeline` and `api`.
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from census.fetch import USER_AGENT  # noqa: E402
from census.tests.t05_country_values import (  # noqa: E402
    _DISAMBIGUATED,
    _display_name,
    _flag_code,
    _is_canonical,
    _iso,
    _vocabulary,
)
from journal_chain import first_break  # noqa: E402
from prod_write import DIGEST_RE, SSH_HOST, pin_line, send  # noqa: E402

from mechanical.lane import T05, Lane, sql_literal  # noqa: E402
from pipeline.utils.country_lookup import canonicalize_country_display_name  # noqa: E402

if TYPE_CHECKING:
    #: Only the annotation of `_geography`, `classify`, `build_plan` and `_atlas`. The module
    #: itself is imported inside those functions - see `_t02()`.
    from census.tests.t02_admin_country import _Atlas

log = logging.getLogger("mechanical.plan")

#: T05's journal identity. The values live on the lane (`mechanical/lane.py`, which explains them);
#: these names stay because the delivered tests, `apply.VERIFY_SQL` and every caller import them.
RUN_STAMP = T05.run_stamp
ROLLBACK_RUN_STAMP = T05.rollback_run_stamp
TEST_ID = T05.test_id
CONFIDENCE = T05.confidence

CURATED_SOURCE = "ancient_nerds"
COUNTRY_COLUMN_CHARS = T05.max_chars
HINT_WORDS = frozenset({"country", "state", "nation", "republic"})
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

DEFAULT_CANDIDATES = REPO / "output/remediation/run_t05/findings.jsonl"
DEFAULT_WORKLIST = REPO / "output/remediation/phase3_worklist/WORKLIST.jsonl"
DEFAULT_SNAPSHOT = REPO / "output/remediation/snapshot/unified_sites.jsonl.gz"
DEFAULT_EXTERNAL_IDS = REPO / "output/remediation/snapshot/site_external_ids.jsonl.gz"
DEFAULT_WITNESSES = REPO / "output/remediation/cache/mechanical_country_witnesses.json"
DEFAULT_OUT = REPO / "output/remediation/mechanical"

WIKIDATA_API = "https://www.wikidata.org/w/api.php"


class PlanError(RuntimeError):
    """A refusal to plan or to render - always fail closed, never a fallback."""


# ------------------------------------------------------------------------------- the inputs
@dataclass(frozen=True)
class Finding:
    """One census T05 finding: the candidate's origin, never the value's source."""

    site_id: str
    test_id: str
    applicable: bool
    current_value: str | None
    proposed_value: str | None
    confidence: str
    severity: str
    note: str
    dimension: str = "classification / country"


@dataclass(frozen=True)
class Site:
    """The object of the write, read from the live database."""

    site_id: str
    name: str
    country: str | None
    lat: float | None
    lon: float | None
    source_id: str


@dataclass(frozen=True)
class Anchor:
    """Where the external witness comes from."""

    qid: str
    via: str


@dataclass(frozen=True)
class Verdict:
    """One candidate, decided. `ok=False` is a refusal and carries the measured reason."""

    site_id: str
    site_name: str
    ok: bool
    old_value: str | None
    new_value: str | None
    rule: str
    reason: str
    note: str
    phase3: bool
    finding_test_id: str
    evidence: tuple[dict[str, Any], ...] = ()
    #: The live input the value was derived from, as text, for a lane with `premise_sql`.
    premise: str | None = None
    #: The cell's column on a cell lane (`lane.cells`); None on a column lane.
    column: str | None = None
    #: The journal row a reversal lane undoes.
    journal_id: int | None = None


def load_findings(path: Path) -> list[Finding]:
    """Every T05 finding, applicable or not - the refusals are part of the result."""
    if not path.exists():
        raise PlanError(f"{path} is missing - run the census first")
    out: list[Finding] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(
                Finding(
                    site_id=str(d["site_id"]),
                    test_id=str(d["test_id"]),
                    applicable=bool(d.get("applicable")),
                    current_value=d.get("current_value"),
                    proposed_value=d.get("proposed_value"),
                    confidence=str(d.get("confidence") or ""),
                    severity=str(d.get("severity") or ""),
                    note=str(d.get("note") or ""),
                )
            )
    if not out:
        raise PlanError(f"{path} holds no findings")
    return out


def load_phase3_sites(path: Path) -> set[str]:
    """Site ids the Phase 3 review worklist owns - per site here, per field in the write."""
    if not path.exists():
        raise PlanError(f"{path} is missing - build the worklist first")
    sites: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("phase3"):
                sites.add(str(d["site_id"]))
    return sites


def load_snapshot_countries(path: Path) -> dict[str, str]:
    """`country` as the census saw it - the third leg of the stale-finding check."""
    if not path.exists():
        raise PlanError(f"{path} is missing - the snapshot is gone")
    out: dict[str, str] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            sid = str(d["id"])
            if d.get("source_id") == CURATED_SOURCE:
                out[sid] = str(d.get("country") or "")
    return out


def load_wikidata_qids(path: Path) -> dict[str, str]:
    """`site_external_ids.kind = 'wikidata_qid'`, where a site has one."""
    if not path.exists():
        raise PlanError(f"{path} is missing - the snapshot is gone")
    out: dict[str, str] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if str(d.get("kind")) == "wikidata_qid" and d.get("value"):
                out[str(d["site_id"])] = str(d["value"])
    return out


# ----------------------------------------------------------------------------- re-derivation
def _plain(part: str) -> str:
    """`Georgia (country)` -> `Georgia`; anything else unchanged."""
    m = _DISAMBIGUATED.match(part.strip())
    return m.group("plain").strip() if m else part.strip()


class CountryNamer(Protocol):
    """What the reduction needs from an atlas: the features' own names, nothing else.

    Narrower than `_Atlas` on purpose, so the hint rule can be tested without Natural Earth and so
    the dependency this module takes on the dataset is visible in one line.
    """

    @property
    def features(self) -> Sequence[Any]: ...


def reduce_value(
    stored: str, codes: Mapping[str, str], normalize: Any, atlas: CountryNamer
) -> tuple[str, str] | None:
    """Reduce a stored value to the plain country name it holds, or None.

    Returns `(plain, rule)`. Two rules, both measured rather than guessed: a trailing
    disambiguation hint, and the comma-separated part that Natural Earth carries as an admin-0
    feature. The country/territory distinction has to come from Natural Earth: both project
    vocabularies answer `CL` for `Easter Island` as readily as for `Chile`, so only the feature
    name decides which of the two the column is meant to hold. Anything else - two candidate
    countries, a part that is empty, a label with no resolvable part - is None, and None is a
    refusal.
    """
    stored = stored.strip()
    if not stored:
        return None
    hint = _DISAMBIGUATED.match(stored)
    if hint:
        plain = hint.group("plain").strip()
        if plain and plain.lower() in HINT_WORDS:
            return None  # `State (country)`: the hint has eaten the whole name
        if _display_name(plain, dict(codes)) and _iso(plain, normalize):
            return plain, "disambiguation-hint"
        return None
    if "," in stored:
        parts = [p.strip() for p in stored.split(",")]
        if any(not p for p in parts):
            return None
        known = [
            p
            for p in (_plain(part) for part in parts)
            if _display_name(p, dict(codes)) and _iso(p, normalize)
        ]
        if len(set(known)) == 1 and known:
            return known[0], "compound-label"
        if len({_iso(p, normalize) for p in known}) == 1 and known:
            countries = [p for p in known if names_a_country(atlas, p)]
            if len(countries) == 1:
                return countries[0], "compound-label-country-part"
        return None
    return None


def names_a_country(atlas: CountryNamer, part: str) -> bool:
    """Does Natural Earth carry an admin-0 feature whose own name is this string?

    The feature's name set (ADMIN, NAME, BRK_NAME, NAME_LONG, NAME_ALT), not the ISO resolution:
    `_Atlas.claim()` maps `Easter Island` through the project's own vocabulary to Chile's polygon,
    which would make the territory look like a country. The feature's own name cannot.
    """
    from census.tests.t02_admin_country import _fold  # the geo stack, imported on use only

    key = _fold(part)
    return any(key == _fold(f.admin) or key in f.name_keys for f in atlas.features)


def _legible(value: str, max_chars: int = COUNTRY_COLUMN_CHARS) -> str | None:
    """Why the string cannot be written into the column at all, or None when it is fine."""
    if value != value.strip():
        return "leading or trailing whitespace"
    if unicodedata.normalize("NFC", value) != value:
        return "not NFC-normalised"
    if len(value) > max_chars:
        return f"{len(value)} characters, longer than the column"
    if any(ch in value for ch in "\r\n\t"):
        return "control characters"
    return None


# ------------------------------------------------------------------------------ the witnesses
def _geography(
    atlas: _Atlas, country: str, lat: float | None, lon: float | None, retrieved_at: str | None
) -> tuple[bool, str, dict[str, Any] | None]:
    """Is the row's own point inside the country the new value names?"""
    from census.tests.t02_admin_country import NE_URL, TOLERANCE_M, _nearest_m

    if lat is None or lon is None:
        return False, "the row carries no usable point to test", None
    claim = atlas.claim(country)
    if claim is None:
        return False, f"Natural Earth has no feature for {country!r}", None
    inside = bool(claim.geom.covers(_point(lon, lat)))
    metres = 0.0 if inside else _nearest_m(claim.geom, lon, lat)[0]
    if not inside and metres > TOLERANCE_M:
        note = (
            f"point ({lat:.5f}, {lon:.5f}) lies {metres / 1000.0:.1f} km outside the "
            f"{'/'.join(claim.matched)} polygon"
        )
        return False, note, None
    evidence = {
        "source": f"naturalearth:ne_10m_admin_0_countries ({'/'.join(claim.matched)})",
        "url": NE_URL,
        "retrieved_at": retrieved_at,
        "quote": (
            f"point ({lat:.5f}, {lon:.5f}) inside the {country!r} polygon"
            if inside
            else f"point ({lat:.5f}, {lon:.5f}) {metres:.0f} m from the nearest {country!r} "
            f"boundary - inside the {TOLERANCE_M:.0f} m this project calls 'the same place'"
        ),
    }
    return True, "", evidence


def _point(lon: float, lat: float) -> Any:
    """A shapely point, imported here because only this module's geography needs it."""
    from shapely.geometry import Point

    return Point(lon, lat)


def check_wikidata(
    anchor: Anchor | None, witness: Mapping[str, Any] | None, iso: str
) -> tuple[bool | None, str, dict[str, Any] | None]:
    """`P17 -> P297` against the derived ISO code: True, False (contradiction) or None (no data).

    Only the **preferred** claims are decisive, because `P17` is a country the subject lies in *or
    has lain in*: Kutaisi carries Georgia as `preferred` (P580 = 1991-04-09) next to the Soviet
    Union, whose `P297` is the withdrawn code `SU`, and the Russian Empire, which has none. Both are
    normal rank, both are history, and neither contradicts the value being written. A decisive value
    whose `P297` disagrees refuses the row; a preferred claim with no `P297` neither matches nor
    contradicts and is recorded as it stands.
    """
    if anchor is None:
        return (
            None,
            "no Wikidata entity: none in site_external_ids and none resolvable by label + coordinate",
            None,
        )
    if witness is None:
        return None, f"{anchor.qid} not in the witness cache - re-collect it", None
    claims = [c for c in (witness.get("p17") or []) if isinstance(c, Mapping)]
    countries = witness.get("countries") or {}
    if not claims:
        return None, f"{anchor.qid} states no P17 (country)", None
    preferred = [c for c in claims if c.get("rank") == "preferred"]
    decisive = preferred or claims
    history = [c for c in claims if c not in decisive]

    def describe(claim: Mapping[str, Any]) -> str:
        qid = str(claim.get("id"))
        entry = countries.get(qid) or {}
        code = entry.get("p297") or "no P297"
        span = ""
        if claim.get("start") or claim.get("end"):
            span = f", {claim.get('start') or '?'}..{claim.get('end') or '?'}"
        return f"{qid} {entry.get('label') or '?'} ({code}{span})"

    resolved = {
        str(c.get("id")): (countries.get(str(c.get("id"))) or {}).get("p297") for c in decisive
    }
    contradicting = {q: c for q, c in resolved.items() if c and c.upper() != iso}
    rank_word = "preferred" if preferred else "only"
    quote = (
        f"{anchor.qid} P17 {rank_word}: "
        + "; ".join(describe(c) for c in decisive)
        + (
            " | history (normal rank): " + "; ".join(describe(c) for c in history)
            if history
            else ""
        )
    )
    if contradicting:
        labels = {q: (countries.get(q) or {}).get("label") for q in contradicting}
        return (
            False,
            f"the {rank_word} P17 {', '.join(f'{q} = {c} ({labels[q]})' for q, c in contradicting.items())}"
            f" contradicts {iso}",
            None,
        )
    matching = [q for q, c in resolved.items() if c and c.upper() == iso]
    if not matching:
        return None, f"no decisive P17 of {anchor.qid} resolves to an ISO code: {quote}", None
    label = (countries.get(matching[0]) or {}).get("label")
    return (
        True,
        "",
        {
            "source": f"wikidata:{anchor.qid}:P17 -> {matching[0]}:P297",
            "url": f"https://www.wikidata.org/entity/{anchor.qid}",
            "retrieved_at": witness.get("fetched_at"),
            "quote": f"{quote} -> ISO 3166-1 alpha-2 {iso} ({label!r}); anchor via {anchor.via}",
        },
    )


# ------------------------------------------------------------------------------- the decision
def classify(
    finding: Finding,
    site: Site,
    *,
    snapshot_country: str | None,
    phase3: bool,
    codes: Mapping[str, str],
    normalize: Any,
    atlas: _Atlas,
    anchor: Anchor | None,
    witness: Mapping[str, Any] | None,
    retrieved_at: str | None,
) -> Verdict:
    """Decide one candidate. Every check is named, and the first failure is the reason."""

    def refuse(reason: str, note: str, evidence: tuple[dict[str, Any], ...] = ()) -> Verdict:
        return Verdict(
            site_id=site.site_id,
            site_name=site.name,
            ok=False,
            old_value=site.country,
            new_value=None,
            rule="",
            reason=reason,
            note=note,
            phase3=phase3,
            finding_test_id=finding.test_id,
            evidence=evidence,
        )

    base: tuple[dict[str, Any], ...] = (
        {
            "source": f"census:{finding.test_id} (candidate origin, not the value's source)",
            "url": "output/remediation/run_t05/findings.jsonl",
            "quote": f"applicable={finding.applicable} proposal={finding.proposed_value!r} "
            f"confidence={finding.confidence} severity={finding.severity}: {finding.note}",
        },
    )

    if not finding.applicable:
        return refuse(
            "finding-not-applicable",
            "the census marked this finding review-only: it names a defect no snapshot can settle "
            "mechanically, so the row is left exactly as it is",
            base,
        )
    if site.source_id != CURATED_SOURCE:
        return refuse(
            "row-not-in-curated-source",
            f"the row belongs to source_id={site.source_id!r}; this lane writes curated sites only",
            base,
        )
    stored = (site.country or "").strip()
    if not stored:
        return refuse("no-country-value", "the row holds no country to repair", base)
    if snapshot_country is not None and snapshot_country != site.country:
        return refuse(
            "snapshot-live-mismatch",
            f"the census read {snapshot_country!r}, the database holds {site.country!r} - the "
            f"finding was made on a different value",
            base,
        )
    if finding.current_value != site.country:
        return refuse(
            "finding-stale",
            f"the finding's current_value is {finding.current_value!r}, the database holds "
            f"{site.country!r}",
            base,
        )

    reduced = reduce_value(stored, codes, normalize, atlas)
    if reduced is None:
        return refuse(
            "no-reduction-rule",
            f"{stored!r} does not reduce to a single country: no disambiguation hint, or a comma "
            f"label without exactly one part Natural Earth carries as an admin-0 state",
            base,
        )
    plain, rule = reduced
    canonical = canonicalize_country_display_name(plain)
    if canonical != finding.proposed_value:
        return refuse(
            "canonicalisation-differs-from-proposal",
            f"the project's canonical form of {stored!r} is {canonical!r}, the finding proposes "
            f"{finding.proposed_value!r}; a refused row is a result, an invented value is not",
            base,
        )
    value = str(canonical)

    if value == site.country:
        return refuse(
            "already-the-value",
            "the row already holds the canonical value; there is nothing to write",
            base,
        )
    illegible = _legible(value)
    if illegible:
        return refuse("value-unwritable", f"{value!r} is {illegible}", base)

    old_iso = _iso(stored, normalize)
    new_iso = _iso(value, normalize)
    if old_iso is None or new_iso is None or old_iso != new_iso:
        return refuse(
            "iso-unchanged-check-failed",
            f"normalize_country({stored!r}) -> {old_iso!r} but normalize_country({value!r}) -> "
            f"{new_iso!r}; the write must not change which country the project reads",
            base,
        )
    vocabulary = {
        "source": "ancient-nerds-map/src/utils/countryFlags.ts:COUNTRY_CODES",
        "url": "ancient-nerds-map/src/utils/countryFlags.ts",
        "quote": f"COUNTRY_CODES[{value!r}] = {codes.get(value)!r}; "
        f"getCountryCode({stored!r}) = {_flag_code(stored, dict(codes))!r} "
        f"(the old value's flag, recorded, not required to match)",
    }
    if value not in codes or codes[value] != new_iso:
        return refuse(
            "not-a-country-code",
            f"{value!r} is not a key of COUNTRY_CODES with the code {new_iso!r} "
            f"(COUNTRY_CODES[{value!r}] = {codes.get(value)!r}), so no flag would render for it",
            base + (vocabulary,),
        )
    lookup = {
        "source": "pipeline/utils/country_lookup.py:NAME_TO_ISO / normalize_country",
        "url": "pipeline/utils/country_lookup.py",
        "quote": f"normalize_country({stored!r}) = {old_iso!r} = normalize_country({value!r}); "
        f"canonicalize_country_display_name({plain!r}) = {canonical!r}",
    }
    ok, note, geo_evidence = _geography(atlas, value, site.lat, site.lon, retrieved_at)
    if not ok:
        return refuse("geography-contradicts", note, base + (lookup, vocabulary))
    witness_ok, witness_note, witness_evidence = check_wikidata(anchor, witness, str(new_iso))
    if witness_ok is False:
        return refuse(
            "wikidata-contradicts",
            witness_note,
            base + (lookup, vocabulary) + ((geo_evidence,) if geo_evidence else ()),
        )
    if not _is_canonical(value, dict(codes), normalize):
        return refuse(
            "not-a-fixed-point",
            f"the census predicate would flag {value!r} again; the write would not settle it",
            base + (lookup, vocabulary),
        )

    evidence = list(base)
    evidence.append(lookup)
    evidence.append(vocabulary)
    if geo_evidence:
        evidence.append(geo_evidence)
    if witness_evidence:
        evidence.append(witness_evidence)
    evidence.append(
        {
            "source": "docs/procedures/SITES_DB_REMEDIATION_2026-09.md:682",
            "url": "docs/procedures/SITES_DB_REMEDIATION_2026-09.md",
            "quote": "Phase 1 item 5: country values `Georgia (country)` 27, "
            "`Chile, Easter Island` 8, `Baltic Sea` 1 - the first two are the "
            "mechanical set, the third is not a country",
        }
    )
    note = f"{stored!r} -> {value!r} (ISO {new_iso})"
    if witness_ok is None:
        note += f"; no external witness: {witness_note}"
    return Verdict(
        site_id=site.site_id,
        site_name=site.name,
        ok=True,
        old_value=site.country,
        new_value=value,
        rule=rule,
        reason="",
        note=note,
        phase3=phase3,
        finding_test_id=finding.test_id,
        evidence=tuple(evidence),
    )


@dataclass(frozen=True)
class Plan:
    """The decided plan: what will be written (`changes`) and what will not (`skipped`)."""

    changes: tuple[Verdict, ...]
    skipped: tuple[Verdict, ...]
    source_id: str = CURATED_SOURCE
    built_at: str = ""
    counters: Mapping[str, int] = field(default_factory=dict)
    #: The lane the plan is written for; its run stamp and test id are the lane's, never a copy.
    lane: Lane = T05

    @property
    def run_stamp(self) -> str:
        return self.lane.run_stamp

    @property
    def test_id(self) -> str:
        return self.lane.test_id

    @property
    def sites(self) -> tuple[str, ...]:
        return tuple(sorted({v.site_id for v in self.changes}))


def build_plan(
    findings: Sequence[Finding],
    sites: Mapping[str, Site],
    *,
    snapshot_countries: Mapping[str, str],
    phase3_sites: set[str],
    codes: Mapping[str, str],
    normalize: Any,
    atlas: _Atlas,
    anchors: Mapping[str, Anchor],
    witnesses: Mapping[str, Any],
    retrieved_at: str | None,
    built_at: str,
) -> Plan:
    """A pure function of its inputs: no network, no database, no clock of its own."""
    verdicts: list[Verdict] = []
    for finding in sorted(findings, key=lambda f: f.site_id):
        site = sites.get(finding.site_id)
        if site is None:
            if finding.applicable:
                reason = "row-missing"
                note = "the site is not in the curated set any more; nothing to write"
            else:
                reason = "finding-not-applicable"
                note = (
                    "the census marked this finding review-only: it names a defect no snapshot can "
                    "settle mechanically, so the row is left exactly as it is"
                )
            verdicts.append(
                Verdict(
                    site_id=finding.site_id,
                    site_name="",
                    ok=False,
                    old_value=None,
                    new_value=None,
                    rule="",
                    reason=reason,
                    note=note,
                    phase3=finding.site_id in phase3_sites,
                    finding_test_id=finding.test_id,
                )
            )
            continue
        verdicts.append(
            classify(
                finding,
                site,
                snapshot_country=snapshot_countries.get(finding.site_id),
                phase3=finding.site_id in phase3_sites,
                codes=codes,
                normalize=normalize,
                atlas=atlas,
                anchor=anchors.get(finding.site_id),
                witness=witnesses.get(finding.site_id),
                retrieved_at=retrieved_at,
            )
        )
    changes = tuple(v for v in verdicts if v.ok)
    skipped = tuple(v for v in verdicts if not v.ok)
    counters = {
        **{f"rule:{k}": v for k, v in Counter(c.rule for c in changes).items()},
        **{f"skip:{k}": v for k, v in Counter(s.reason for s in skipped).items()},
        "changes": len(changes),
        "skipped": len(skipped),
        "changes_on_phase3_sites": sum(1 for c in changes if c.phase3),
    }
    return Plan(
        changes=changes,
        skipped=skipped,
        built_at=built_at,
        counters=counters,
    )


# --------------------------------------------------------------------------- the live database
def load_sites(site_ids: Iterable[str], *, reader: Any, strict: bool = True) -> dict[str, Site]:
    """The rows to be written, read from production. `reader` is injected for the tests.

    `strict` is for the rows that will be written: a write target that is not in the database is a
    failure, not a refusal. The rows only reported on (the census's non-applicable findings) are
    read tolerantly, so a row that has since been deleted shows up as a refusal with a reason
    instead of stopping the whole run.
    """
    ids = sorted({str(s) for s in site_ids})
    listed = sql_ids(ids)
    if not ids:
        return {}
    sql = (
        "SELECT id, name, coalesce(country, '<NULL>'), "
        "coalesce(lat::text, ''), coalesce(lon::text, ''), source_id "
        f"FROM unified_sites WHERE id::text IN ({listed})"
    )
    out: dict[str, Site] = {}
    for row in reader(sql):
        sid, name, country, lat, lon, source = row
        out[str(sid)] = Site(
            site_id=str(sid),
            name=str(name),
            country=None if country == "<NULL>" else str(country),
            lat=float(lat) if lat not in ("", None) else None,
            lon=float(lon) if lon not in ("", None) else None,
            source_id=str(source),
        )
    if strict:
        missing = sorted(set(ids) - set(out))
        if missing:
            raise PlanError(
                f"{len(missing)} planned site(s) are not in the database: {missing[:3]}"
            )
    return out


# ------------------------------------------------------------------------------- the witnesses
def get_json(endpoint: str, params: Mapping[str, str], *, timeout: int = 60) -> dict[str, Any]:
    """One GET with the project's `USER_AGENT`, parsed as JSON - one attempt, no mirror loop."""
    url = endpoint + "?" + urllib.parse.urlencode(dict(params))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # one attempt, no mirror loop: a failure must be visible
        raise PlanError(f"request failed: {url}: {exc}") from exc


def _wikidata(params: Mapping[str, str], *, timeout: int = 60) -> dict[str, Any]:
    return get_json(
        WIKIDATA_API, {**params, "format": "json", "formatversion": "2"}, timeout=timeout
    )


def _claims(entity: Mapping[str, Any], prop: str) -> list[Any]:
    return [c for c in (entity.get("claims") or {}).get(prop, []) if c.get("rank") != "deprecated"]


def _claim_time(claim: Mapping[str, Any], prop: str) -> str | None:
    """A qualifier's time value as text, for the evidence quote (P580/P582)."""
    for qualifier in (claim.get("qualifiers") or {}).get(prop, []):
        value = (qualifier.get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("time"):
            return str(value["time"])[:10]
    return None


def _p17_claims(entity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every non-deprecated P17 with its rank and, where Wikidata gives them, its years.

    The rank is what makes the witness usable: `P17` is a country the subject lies in *or has lain
    in*, so a historic site legitimately carries the Soviet Union and the Russian Empire next to the
    country it is in today. Deprecated claims are dropped; normal-rank ones are kept as history.
    """
    out: list[dict[str, Any]] = []
    for claim in _claims(entity, "P17"):
        value = (claim.get("mainsnak") or {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            out.append(
                {
                    "id": str(value["id"]),
                    "rank": str(claim.get("rank") or "normal"),
                    "start": _claim_time(claim, "P580"),
                    "end": _claim_time(claim, "P582"),
                }
            )
    return out


def _coordinate(entity: Mapping[str, Any]) -> tuple[float, float] | None:
    for claim in _claims(entity, "P625"):
        value = (claim.get("mainsnak") or {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("latitude") is not None:
            return float(value["latitude"]), float(value["longitude"])
    return None


def resolve_anchors(sites: Mapping[str, Site], known_qids: Mapping[str, str]) -> dict[str, Anchor]:
    """An entity per site: the stored qid, or one proved by label **and** coordinate.

    The second path exists for the two ahu that have no `site_external_ids` row. It is a
    measurement, not a guess: the search must return exactly one entity whose English label is
    the row's own name, and that entity's `P625` must be within 1000 m of the row's point.
    """
    from census.tests.t02_admin_country import TOLERANCE_M

    anchors: dict[str, Anchor] = {
        sid: Anchor(qid, "site_external_ids:wikidata_qid")
        for sid, qid in known_qids.items()
        if sid in sites
    }
    todo = sorted(set(sites) - set(anchors))
    for sid in todo:
        site = sites[sid]
        found = (
            _wikidata(
                {"action": "wbsearchentities", "search": site.name, "language": "en", "limit": "5"}
            ).get("search")
            or []
        )
        hits = [
            str(h["id"])
            for h in found
            if str(h.get("label") or "").strip().casefold() == site.name.strip().casefold()
        ]
        if len(hits) != 1:
            log.warning(
                "no unique Wikidata entity for %r (%d label match(es))", site.name, len(hits)
            )
            continue
        entity = (
            _wikidata({"action": "wbgetentities", "ids": hits[0], "props": "claims"}).get(
                "entities"
            )
            or {}
        ).get(hits[0]) or {}
        point = _coordinate(entity)
        if point is None or site.lat is None or site.lon is None:
            log.warning("%s: no P625 to check the identity against", hits[0])
            continue
        from pyproj import Geod

        metres = Geod(ellps="WGS84").inv(site.lon, site.lat, point[1], point[0])[2]
        if metres > TOLERANCE_M:
            log.warning(
                "%s: %s is %.0f m from the row's point - not the same place",
                site.name,
                hits[0],
                metres,
            )
            continue
        anchors[sid] = Anchor(hits[0], f"wikidata:label+coordinate ({metres:.0f} m)")
    return anchors


def fetch_entities(qids: Iterable[str], props: str, **extra: str) -> dict[str, Any]:
    """`wbgetentities` for `qids`, 40 per request; a missing entity is an error, not a gap."""
    wanted = sorted(set(qids))
    entities: dict[str, Any] = {}
    for chunk in [wanted[i : i + 40] for i in range(0, len(wanted), 40)]:
        got = (
            _wikidata(
                {"action": "wbgetentities", "ids": "|".join(chunk), "props": props, **extra}
            ).get("entities")
            or {}
        )
        for qid, entity in got.items():
            if entity.get("missing"):
                raise PlanError(f"{qid} is missing on Wikidata")
            entities[qid] = entity
    return entities


def country_codes(country_qids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """`P297` (ISO 3166-1 alpha-2) and the English label of every country entity named."""
    return {
        qid: {
            "label": ((entity.get("labels") or {}).get("en") or {}).get("value"),
            "p297": next(iter(_claim_strings(entity, "P297")), None),
        }
        for qid, entity in fetch_entities(country_qids, "claims|labels", languages="en").items()
    }


def collect_witnesses(
    sites: Mapping[str, Site], anchors: Mapping[str, Anchor], *, fetched_at: str
) -> dict[str, Any]:
    """`P17` for every site's entity, then `P297` + label for every country it names."""
    qids = sorted({a.qid for a in anchors.values()})
    if not qids:
        raise PlanError("no Wikidata entity for any candidate - the external witness is empty")
    site_claims = {
        qid: _p17_claims(entity) for qid, entity in fetch_entities(qids, "claims").items()
    }
    countries = sorted({str(c["id"]) for claims in site_claims.values() for c in claims})
    country_claims = country_codes(countries)
    return {
        "generated_at": fetched_at,
        "endpoint": WIKIDATA_API,
        "user_agent": USER_AGENT,
        "sites": {
            sid: {
                "qid": anchor.qid,
                "via": anchor.via,
                "name": sites[sid].name,
                "p17": site_claims.get(anchor.qid, []),
                "countries": country_claims,
                "fetched_at": fetched_at,
            }
            for sid, anchor in sorted(anchors.items())
        },
        "countries": country_claims,
    }


def _claim_strings(entity: Mapping[str, Any], prop: str) -> list[str]:
    out: list[str] = []
    for claim in _claims(entity, prop):
        value = (claim.get("mainsnak") or {}).get("datavalue", {}).get("value")
        if isinstance(value, str) and value.strip():
            out.append(value.strip())
    return out


def load_witnesses(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PlanError(f"{path} is missing - run plan.py --collect first (it needs the network)")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------- the output
#: A SQL literal, for the human-readable `condition` the plan records per row - the lane's own
#: quoting rule, not a second copy of it.
_quoted = sql_literal


def plan_record(change: Verdict, plan: Plan) -> dict[str, Any]:
    """One `PLAN.jsonl` line: the row, its lane's journal identity, and its evidence.

    On a cell lane the line names the cell's column and table, and the change key names the cell;
    on a column lane every line is exactly what it was before cell lanes existed.
    """
    lane = plan.lane
    column = change.column if lane.cells else lane.column
    if lane.cells:
        lane.cell(column)
    target = lane.target
    record: dict[str, Any] = {
        "site_id": change.site_id,
        "site_name": change.site_name,
        "table": target.table,
        "column": column,
        "key_column": target.key_column,
        "old_value": change.old_value,
        "new_value": change.new_value,
        "rule": change.rule,
        "condition": f"{target.key_column} = {change.site_id} AND {column} IS NOT DISTINCT FROM "
        f"{_quoted(change.old_value)}",
        "reason": f"{lane.key_prefix} ({change.rule}): {change.note}",
        "change_key": lane.change_key(change.site_id, change.column if lane.cells else None),
        "test_id": plan.test_id,
        "run_stamp": plan.run_stamp,
        "confidence": lane.confidence,
        "source_id": plan.source_id,
        "phase3": change.phase3,
        "finding_test_id": change.finding_test_id,
        "evidence": list(change.evidence),
    }
    if lane.premise_sql is not None:
        if change.premise is None:
            raise PlanError(f"{change.site_id}: the {lane.name} lane needs the row's premise")
        if not lane.cells:
            # A cell lane's premise expression is the lane's, named once in its PLAN.md: repeated
            # on each of 6,000 card_stats cells it was 6 MB of the same kilobyte.
            record["premise_sql"] = lane.premise_sql
        record["premise"] = change.premise
    if lane.reverses_journal:
        if change.journal_id is None:
            raise PlanError(
                f"{change.site_id}: the {lane.name} lane needs the journal row it undoes"
            )
        record["journal_id"] = change.journal_id
    return record


def write_plan_jsonl(plan: Plan, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for change in plan.changes:
            fh.write(json.dumps(plan_record(change, plan), ensure_ascii=False) + "\n")
    return len(plan.changes)


def write_skipped_jsonl(plan: Plan, path: Path) -> int:
    """Every candidate that is not written, with the reason - refusals are results."""
    path.parent.mkdir(parents=True, exist_ok=True)
    skipped = list(plan.skipped)
    written: set[str] = set()
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for verdict in skipped:
            written.add(verdict.site_id)
            fh.write(
                json.dumps(
                    {
                        "site_id": verdict.site_id,
                        "site_name": verdict.site_name,
                        "table": plan.lane.target.table,
                        "column": verdict.column if plan.lane.cells else plan.lane.column,
                        "current_value": verdict.old_value,
                        "proposed_value": verdict.new_value,
                        "reason": verdict.reason,
                        "note": verdict.note,
                        "phase3": verdict.phase3,
                        "finding_test_id": verdict.finding_test_id,
                        "evidence": list(verdict.evidence),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return len(written)


def write_plan_md(plan: Plan, path: Path, extra: Mapping[str, Any]) -> None:
    """The reviewable summary: what will be written, what will not, and on what evidence."""
    by_value = Counter((c.old_value, c.new_value) for c in plan.changes)
    lines: list[str] = []
    add = lines.append
    add("# Mechanical country repair - plan")
    add("")
    add(
        f"Built {plan.built_at} by `scripts/remediation/mechanical/plan.py`. "
        f"Run stamp `{plan.run_stamp}`, journal test id `{plan.test_id}`, "
        f"source `{plan.source_id}`."
    )
    add("")
    add(
        f"**{len(plan.changes)} row(s) will be written, {len(plan.skipped)} candidate(s) refused.** "
        f"{plan.counters.get('changes_on_phase3_sites', 0)} of the written rows are sites the Phase 3 "
        "worklist also holds - their T01/T03 findings stay Phase 3's; only `country` is written here."
    )
    add("")
    add("## The set: 35, not the worklist's 27")
    add("")
    add(extra["set_note"])
    add("")
    add("| stored value | written value | rows | rule |")
    add("|---|---|---|---|")
    for (old, new), count in sorted(by_value.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        rule = next(c.rule for c in plan.changes if (c.old_value, c.new_value) == (old, new))
        add(f"| `{old}` | `{new}` | {count} | {rule} |")
    add("")
    add("## Every check, and what it measured")
    add("")
    add("| check | source | what it proves |")
    add("|---|---|---|")
    for check, source, proves in extra["checks"]:
        add(f"| {check} | {source} | {proves} |")
    add("")
    add("## Witness coverage")
    add("")
    add(extra["coverage"])
    add("")
    add("## Refusals")
    add("")
    add("| reason | candidates | what it means |")
    add("|---|---|---|")
    for reason, meaning in extra["refusal_meaning"]:
        count = plan.counters.get(f"skip:{reason}", 0)
        if count:
            add(f"| `{reason}` | {count} | {meaning} |")
    add("")
    add(
        f"All {len(plan.skipped)} refusals are in `SKIPPED.jsonl` with the measurement that "
        "produced them. None of them is deleted, and none of them is written."
    )
    add("")
    add("## What a restart does to this column")
    add("")
    add(extra["restart"])
    add("")
    add("## Reproduce")
    add("")
    add("```bash")
    for command in extra["commands"]:
        add(command)
    add("```")
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def reversed_records(records: Sequence[Any], lane: Lane = T05) -> list[Any]:
    """The reversal of a set of changes: old and new swapped, one record per row.

    Takes anything carrying `site_id`, `site_name`, `old_value`, `new_value`, `rule`, `evidence`,
    `phase3` and `premise` - a `Verdict` from the plan, or an `apply.ChangeRecord` read back out of
    the delivered `PLAN.jsonl`. Both produce the same records, which is what makes the delivered
    `ROLLBACK.sql` reproducible from the delivered plan (measured: byte-identical, see
    `evidence/11_fingerprints.txt`). The premise is kept: a lane never writes the input its value
    was derived from, so the reversal is conditioned on the same one.
    """
    from mechanical import apply as apply_mod

    if lane.cells:
        # A cell's reversal restores its old value in its own column - NULL too, where the lane
        # filled an empty cell. The journal row it undoes is the write's own, unknown until the
        # write has run, so the reversal names none (guard 6 checks a forward reversal only).
        return [
            apply_mod.ChangeRecord(
                site_id=r.site_id,
                site_name=r.site_name,
                old_value=r.new_value,
                new_value=r.old_value,
                rule=f"rollback-{r.rule}",
                condition=f"{lane.target.key_column} = {r.site_id} AND {r.column} IS NOT "
                f"DISTINCT FROM {_quoted(r.new_value)}",
                reason=f"rollback of {lane.key_prefix}: {r.column} {r.old_value!r} restored on "
                f"{r.site_name}",
                evidence=tuple(r.evidence),
                phase3=r.phase3,
                premise=r.premise,
                column=r.column,
            )
            for r in reversed(list(records))
        ]
    return [
        apply_mod.ChangeRecord(
            site_id=r.site_id,
            site_name=r.site_name,
            old_value=str(r.new_value),
            new_value=str(r.old_value),
            rule=f"rollback-{r.rule}",
            condition=f"id = {r.site_id} AND {lane.column} IS NOT DISTINCT FROM "
            f"{_quoted(r.new_value)}",
            reason=f"rollback of {lane.key_prefix}: {r.old_value!r} restored on {r.site_name}",
            evidence=tuple(r.evidence),
            phase3=r.phase3,
            premise=r.premise,
        )
        for r in reversed(list(records))
    ]


def render_rollback_sql(
    records: Sequence[Any],
    *,
    site_ids: Iterable[str],
    source_id: str = CURATED_SOURCE,
    lane: Lane = T05,
) -> str:
    """The reversal of `records`, rendered - the one place the undo is produced.

    `rollback=True` gives every journal row the reversal's own `change_key`: the undo of
    `Georgia (country) -> Georgia` is the different transition `Georgia -> Georgia (country)`, and
    one key for both would make the two indistinguishable in `remediation_change_log`.
    """
    from mechanical import apply as apply_mod

    return apply_mod.render_transaction(
        reversed_records(records, lane),
        run_stamp=lane.rollback_run_stamp,
        site_ids=site_ids,
        source=source_id,
        rollback=True,
        lane=lane,
    )


def write_rollback_sql(plan: Plan, path: Path, *, plan_path: Path) -> int:
    """The reversal, written **before** the apply file - both from the same generator - and pinned
    to the `PLAN.jsonl` it reverses, which must already be written."""
    sql = render_rollback_sql(
        plan.changes, site_ids=plan.sites, source_id=plan.source_id, lane=plan.lane
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pinned(sql, plan_sha256(plan_path)), encoding="utf-8", newline="\n")
    return len(plan.changes)


# ------------------------------------------------------------------------------------ the pin
def plan_sha256(path: Path) -> str:
    """sha256 of a `PLAN.jsonl` as text with LF line endings.

    Text, not bytes: the plan is committed, and `core.autocrlf=true` checks the same commit out
    with CRLF (measured on the delivered T05 plan: raw bytes da4201ef.. in a worktree, cc2e885f..
    in the main tree, identical as text). A digest of the bytes would refuse a correct statement on
    one checkout and pass it on the other.
    """
    if not path.exists():
        raise PlanError(f"{path} does not exist - there is no plan to pin a statement to")
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def pinned(sql: str, digest: str) -> str:
    """`sql` with the pin as its first line: `-- plan sha256 <digest>` (a SQL comment)."""
    return pin_line(digest) + "\n" + sql


def verify_pinned(path: Path, *, plan_path: Path, expected: str) -> str:
    """The statement in `path` - only if it is `expected`, pinned to the plan as it is now.

    Refuses a file without a pin (not emitted from a plan, or edited), with more than one, pinned to
    another digest (the plan changed after the emit: re-emit and re-rehearse), or whose body is not
    what the plan renders (edited after the emit). Read in text mode, like the plan.
    """
    if not path.exists():
        raise PlanError(f"{path} does not exist - emit it from the plan first")
    text = path.read_text(encoding="utf-8")
    declared = DIGEST_RE.findall(text)
    if not declared:
        raise PlanError(
            f"{path.name} carries no '-- plan sha256' pin - it was not emitted from a plan, or it "
            "was edited; refusing to send it to production"
        )
    if len(declared) > 1:
        raise PlanError(f"{path.name} carries {len(declared)} pins - one statement, one plan")
    digest = plan_sha256(plan_path)
    if declared[0] != digest:
        raise PlanError(
            f"{path.name} was rendered from plan sha256 {declared[0]}, but {plan_path.name} now "
            f"hashes to {digest}: the plan changed after the statement was emitted - re-emit and "
            "re-rehearse before anything is sent"
        )
    if text != pinned(expected, digest):
        raise PlanError(
            f"{path.name} is pinned to this plan but is not the statement the plan renders - it was "
            "edited after the emit; refusing to send it to production"
        )
    return text


# ------------------------------------------------------------------------------------- CLI
def _atlas() -> tuple[_Atlas, str | None]:
    """Natural Earth's admin-0 polygons, from the census cache.

    The census T02 module is imported here, not at module level: it imports `geopandas` and
    `pyproj` at module level, and the CI `tests` job installs neither
    (`.github/workflows/ci.yml:184` installs `-r requirements-api.txt -r requirements.lyra.txt`,
    and geopandas/pyproj occur 0 times in both). Importing it at module level made every
    collection of `tests/remediation/test_mechanical.py` raise ModuleNotFoundError in CI, which
    turned the `tests` job red and skipped `deploy`. Only the dataset paths need the geo stack;
    the guarded tests skip without it, exactly as `tests/remediation/test_t02.py` does.
    """
    from census.tests.t02_admin_country import _Atlas, _dataset_dir, _load_features

    dataset = _dataset_dir(REPO / "output/remediation/cache")
    shapefile = dataset / "ne_10m_admin_0_countries.shp"
    if not shapefile.exists():
        raise PlanError(f"{shapefile} is missing - the census collects it (T02 collect)")
    state = dataset / "source.json"
    retrieved = (
        json.loads(state.read_text(encoding="utf-8")).get("fetched_at") if state.exists() else None
    )
    return _Atlas(_load_features(shapefile)), retrieved


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _psql_reader() -> Any:
    """A reader over the production database, the way this project does it: ssh + psql."""
    from mechanical import apply as apply_mod

    def read(sql: str) -> list[list[str]]:
        proc = apply_mod.run_psql(sql, rows=True)
        rows: list[list[str]] = []
        for line in proc.stdout.splitlines():
            if line.strip():
                rows.append(line.split("|"))
        return rows

    return read


def psql_json_reader() -> Callable[[str], list[dict[str, Any]]]:
    """Rows from production as JSON objects, one per line - a name may contain the `|` that
    unaligned psql separates on, so the later lanes read `row_to_json` instead of splitting."""
    from mechanical import apply as apply_mod

    def read(sql: str) -> list[dict[str, Any]]:
        proc = apply_mod.run_psql(f"SELECT row_to_json(t) FROM ({sql}) t", rows=True)
        return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]

    return read


def sql_ids(ids: Iterable[str]) -> str:
    """A SQL list of UUID literals; anything that is not a UUID is refused, never interpolated."""
    wanted = sorted(set(ids))
    for sid in wanted:
        if not UUID_RE.match(sid):
            raise PlanError(f"{sid!r} is not a UUID - refusing to interpolate it")
    return ", ".join(sql_literal(sid) for sid in wanted)


# ------------------------------------------------------------------------- the tagged export
#: The kind of the one line a tagged export ends with: the snapshot's own clock.
SNAPSHOT_KIND = "snapshot"
#: A kind is spliced into a SQL string literal: lowercase letters and underscores, nothing else.
_EXPORT_KIND = re.compile(r"^[a-z_]+$")


def tagged_export_script(parts: Sequence[tuple[str, str]]) -> str:
    """One read-only, repeatable-read transaction: every row of each `(kind, sql)` part as one
    JSON object tagged with its kind, then one `snapshot` line with the transaction's `now()`.

    One snapshot, so the parts are read at the same instant; `QUIET` keeps psql's `BEGIN`/`COMMIT`
    tags out of the output. The cell lanes read production this way (`card_stats.py`, `scope.py`).
    """
    for kind, _sql in parts:
        if not _EXPORT_KIND.match(kind) or kind == SNAPSHOT_KIND:
            raise PlanError(f"{kind!r} is not a kind a tagged export can carry")
    return (
        "\\set QUIET on\nBEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        + "".join(
            f"SELECT json_build_object('kind', '{kind}', 'row', row_to_json(t)) FROM ({sql}) t;\n"
            for kind, sql in parts
        )
        + f"SELECT json_build_object('kind', '{SNAPSHOT_KIND}', 'row', json_build_object("
        "'exported_at', now()::text));\nCOMMIT;\n"
    )


def parse_tagged_export(text: str, kinds: Iterable[str]) -> tuple[dict[str, list[dict]], str]:
    """The rows of each kind and the snapshot's `exported_at`, from `tagged_export_script`'s output.

    A line of a kind the caller did not ask for is refused, and so is an export without exactly
    one snapshot line: psql stops at the first error, so a missing snapshot line is an export
    that did not finish.
    """
    rows: dict[str, list[dict]] = {kind: [] for kind in kinds}
    stamps: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        kind = payload.get("kind")
        if kind == SNAPSHOT_KIND:
            stamps.append(str(payload["row"]["exported_at"]))
        elif kind in rows:
            rows[kind].append(payload["row"])
        else:
            raise PlanError(f"the export holds a line of kind {kind!r}: {line[:80]!r}")
    if len(stamps) != 1:
        raise PlanError(f"the export must hold one snapshot line, it has {len(stamps)}")
    return rows, stamps[0]


def write_tagged_export(script: str, path: Path, *, host: str = SSH_HOST) -> Path:
    """Send a tagged export to production (read-only) and keep its output as it came."""
    proc = send(script, host=host, rows=True, timeout=900)
    if proc.returncode != 0:
        raise PlanError(f"the export failed (psql exit {proc.returncode}): {proc.stderr.strip()}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(proc.stdout, encoding="utf-8", newline="\n")
    return path


# ------------------------------------------------------------------------------- the journal
@dataclass(frozen=True)
class JournalLink:
    """One `remediation_change_log` row for one site's field."""

    id: int
    run_stamp: str
    test_id: str
    old_value: str | None
    new_value: str | None


def load_journal(
    reader: Callable[[str], list[dict[str, Any]]], column: str, site_ids: Iterable[str]
) -> dict[str, tuple[JournalLink, ...]]:
    """Every journal row for `unified_sites.<column>` of these sites, oldest first - read-only."""
    ids = list(site_ids)
    if not ids:
        return {}
    out: dict[str, list[JournalLink]] = {}
    for r in reader(
        "SELECT id, row_pk, run_stamp, coalesce(test_id, '') AS test_id, old_value, new_value "
        "FROM remediation_change_log WHERE table_name = 'unified_sites' "
        f"AND column_name = {sql_literal(column)} AND row_pk IN ({sql_ids(ids)}) ORDER BY id"
    ):
        out.setdefault(str(r["row_pk"]), []).append(
            JournalLink(
                int(r["id"]), str(r["run_stamp"]), str(r["test_id"]), r["old_value"], r["new_value"]
            )
        )
    return {sid: tuple(links) for sid, links in out.items()}


def journal_break(links: Sequence[JournalLink], live: str | None) -> tuple[str, str] | None:
    """`(reason, note)` when a field's journal does not end at its live value, else None.

    Each link must start where the one before it ended, and the last must have written the value
    the row holds: otherwise something wrote the field around the journal, and a plan built on
    the live value would supersede a write nobody can account for. The continuity rule is
    `journal_chain.first_break`, the one the phase-3 acceptance judges the same chains with.
    """
    at = first_break([(link.old_value, link.new_value) for link in links])
    if at is not None:
        before, after = links[at - 1], links[at]
        return (
            "journal-chain-broken",
            f"journal row {after.id} starts from {after.old_value!r}, but the row before it "
            f"({before.id}) ended at {before.new_value!r}",
        )
    if links and links[-1].new_value != live:
        last = links[-1]
        return (
            "journal-disagrees",
            f"the last journal row ({last.id}, {last.run_stamp}) wrote {last.new_value!r}, the "
            f"row holds {live!r} - something wrote it without the journal",
        )
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the mechanical country repairs")
    ap.add_argument("--findings", type=Path, default=DEFAULT_CANDIDATES)
    ap.add_argument("--worklist", type=Path, default=DEFAULT_WORKLIST)
    ap.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    ap.add_argument("--external-ids", type=Path, default=DEFAULT_EXTERNAL_IDS)
    ap.add_argument("--witnesses", type=Path, default=DEFAULT_WITNESSES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--collect",
        action="store_true",
        help="ask Wikidata for the P17/P297 witnesses and cache them (network)",
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="write PLAN.jsonl, PLAN.md, SKIPPED.jsonl, ROLLBACK.sql (reads prod)",
    )
    ap.add_argument(
        "--render-rollback",
        action="store_true",
        help=(
            "re-render ROLLBACK.sql from the delivered PLAN.jsonl alone - no database, no "
            "dataset, no re-collection. The undo is a function of the plan it reverses, so it "
            "stays checkable after the write; re-rendering cannot change its bytes"
        ),
    )
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.render_rollback:
        from mechanical import apply as apply_mod

        plan_file = args.out / "PLAN.jsonl"
        records = apply_mod.load_records(plan_file)
        sql = render_rollback_sql(records, site_ids={r.site_id for r in records})
        target = args.out / "ROLLBACK.sql"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(pinned(sql, plan_sha256(plan_file)), encoding="utf-8", newline="\n")
        log.info("wrote %s (%d row(s)) from %s", target, len(records), plan_file)
        return 0

    findings = load_findings(args.findings)
    applicable = [f for f in findings if f.applicable]
    phase3 = load_phase3_sites(args.worklist)
    snapshot = load_snapshot_countries(args.snapshot)
    qids = load_wikidata_qids(args.external_ids)
    codes, normalize = _vocabulary()
    atlas, retrieved = _atlas()

    if args.collect:
        ids = [f.site_id for f in applicable]
        sites = load_sites(ids, reader=_psql_reader())
        anchors = resolve_anchors(sites, qids)
        log.info("anchors: %d of %d candidate(s)", len(anchors), len(sites))
        payload = collect_witnesses(sites, anchors, fetched_at=_now())
        args.witnesses.parent.mkdir(parents=True, exist_ok=True)
        args.witnesses.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        log.info(
            "wrote %s (%d site(s), %d country entity/ies)",
            args.witnesses,
            len(payload["sites"]),
            len(payload["countries"]),
        )
        return 0

    if not args.write:
        ap.print_help()
        return 0

    witnesses = load_witnesses(args.witnesses)
    write_targets = load_sites([f.site_id for f in applicable], reader=_psql_reader())
    reported = load_sites(
        [f.site_id for f in findings if not f.applicable], reader=_psql_reader(), strict=False
    )
    sites = {**reported, **write_targets}
    anchors = {
        sid: Anchor(str(entry["qid"]), str(entry["via"]))
        for sid, entry in (witnesses.get("sites") or {}).items()
    }
    countries = witnesses.get("countries") or {}
    witness_by_site = {
        sid: {
            "p17": entry.get("p17") or [],
            "countries": countries,
            "fetched_at": entry.get("fetched_at"),
        }
        for sid, entry in (witnesses.get("sites") or {}).items()
    }
    plan = build_plan(
        findings,
        sites,
        snapshot_countries=snapshot,
        phase3_sites=phase3,
        codes=codes,
        normalize=normalize,
        atlas=atlas,
        anchors=anchors,
        witnesses=witness_by_site,
        retrieved_at=retrieved,
        built_at=_now(),
    )
    reviewed = [f for f in findings if not f.applicable]
    extra = _report_inputs(plan, findings, reviewed, sites, anchors, witness_by_site)
    args.out.mkdir(parents=True, exist_ok=True)
    rows = write_plan_jsonl(plan, args.out / "PLAN.jsonl")
    skipped = write_skipped_jsonl(plan, args.out / "SKIPPED.jsonl")
    write_plan_md(plan, args.out / "PLAN.md", extra)
    # ROLLBACK before APPLY, both generated - never hand-typed, and in this order on disk.
    rollback = write_rollback_sql(
        plan, args.out / "ROLLBACK.sql", plan_path=args.out / "PLAN.jsonl"
    )
    log.info("PLAN.jsonl %d rows; SKIPPED.jsonl %d; ROLLBACK.sql %d", rows, skipped, rollback)
    print(json.dumps(plan.counters, indent=1, sort_keys=True))
    return 0


def _report_inputs(
    plan: Plan,
    findings: Sequence[Finding],
    reviewed: Sequence[Finding],
    sites: Mapping[str, Site],
    anchors: Mapping[str, Anchor],
    witnesses: Mapping[str, Any],
) -> dict[str, Any]:
    """The prose the plan file carries, built from the measured numbers."""
    worklist_only = [c for c in plan.changes if c.phase3]
    set_note = (
        f"The candidates are the {len(findings)} T05 findings over {len({f.site_id for f in findings})} "
        f"distinct sites; {len([f for f in findings if f.applicable])} of them are `applicable=true` "
        "and all of those are `proposal=set`. "
        "`output/remediation/phase3_worklist/MECHANICAL.md` lists 27 sites because "
        "`build_worklist.py` also filters `AND NOT phase3`; the 8 it drops carry the same "
        "applicable country finding next to a non-applicable T01/T03 finding about a *different "
        "field*. On the supervisor's decision of 2026-09-21 all 35 are written, because writing 27 "
        "would leave each country split across two hub slugs: 20 of the 27 Georgia rows would join "
        "the 3 rows already at `/sites/georgia` while the other 7 (all of them Phase-3 sites) stayed "
        "at `/sites/georgia-country`, and 7 of the 8 Chile rows would join the 3 already at "
        "`/sites/chile` while Easter Island stayed at `/sites/chile-easter-island` - a half-migrated "
        "state no rule produces. The 8 stay in the "
        "Phase 3 worklist; theirs are "
        + ", ".join(sorted(c.site_name for c in worklist_only))
        + ". The hub split is measured against the database before and after the write "
        "(`apply.py --interests`); the measured table is in `APPLIED.md`."
    )
    with_witness = sum(
        1 for c in plan.changes if any(str(e["source"]).startswith("wikidata:") for e in c.evidence)
    )
    by_anchor = Counter(
        a.via.split(" (")[0]
        for sid, a in anchors.items()
        if sid in {c.site_id for c in plan.changes}
    )
    without_witness = [
        c.site_name
        for c in plan.changes
        if not any(str(e["source"]).startswith("wikidata:") for e in c.evidence)
    ]
    coverage = (
        f"{len(plan.changes)} written row(s); {with_witness} carry a Wikidata `P17 -> P297` "
        f"witness. The {len(without_witness)} without one are "
        + (", ".join(without_witness) if without_witness else "none")
        + ": its Wikidata entity states no `P17` at all, which is recorded per row in "
        "`PLAN.jsonl` as a gap rather than a pass. Every written row carries the two project "
        "vocabularies and the Natural Earth point-in-polygon check; the Wikidata witness is the "
        f"only optional one. Anchors: {dict(by_anchor)}."
    )
    checks = [
        (
            "reduction",
            "the stored string",
            "a hint or a single resolvable comma part; two candidates refuse",
        ),
        (
            "canonical form",
            "pipeline/utils/country_lookup.py:canonicalize_country_display_name",
            "the written value is the project's own canonical string and equals the proposal",
        ),
        (
            "vocabulary 1",
            "pipeline/utils/country_lookup.py:normalize_country",
            "old and new map to the same ISO-3166-1 alpha-2 code",
        ),
        (
            "vocabulary 2",
            "ancient-nerds-map/src/utils/countryFlags.ts:COUNTRY_CODES",
            "the new value is a key carrying that code, so the flag renders",
        ),
        (
            "geography",
            "naturalearth:ne_10m_admin_0_countries (10m, cached, sha256 ce1ac703)",
            "the row's own point is inside the named country's polygon (T02's 1000 m tolerance)",
        ),
        (
            "external",
            "wikidata:P17 -> P297",
            "an independent authority states the same ISO code; a contradicting P17 refuses the row",
        ),
        (
            "fixed point",
            "census T05 predicate",
            "the census would not flag the written value again",
        ),
    ]
    refusal_meaning = [
        (
            "finding-not-applicable",
            "T05 named a defect no snapshot can settle (spelling split, vocabulary gap, not a country)",
        ),
        (
            "no-reduction-rule",
            "the value does not reduce to exactly one country both vocabularies know",
        ),
        (
            "canonicalisation-differs-from-proposal",
            "the project's canonical form disagrees with the census proposal",
        ),
        (
            "not-a-country-code",
            "the value is not a COUNTRY_CODES key with that code - no flag would render",
        ),
        ("iso-unchanged-check-failed", "the write would change which country the project reads"),
        ("geography-contradicts", "the row's point is outside the named country's polygon"),
        ("wikidata-contradicts", "Wikidata's P17 names a different ISO code"),
        ("not-a-fixed-point", "the census would flag the written value again"),
        ("snapshot-live-mismatch", "the census read a value the database no longer holds"),
        ("finding-stale", "the finding's current_value is not the row's value"),
        ("row-missing", "the site is not in the curated set any more"),
        (
            "row-not-in-curated-source",
            "the row belongs to another source and this lane writes curated rows only",
        ),
        ("no-country-value", "there is no country to repair"),
        ("already-the-value", "the row already holds the canonical value"),
        (
            "value-unwritable",
            "the value is not NFC, too long, or carries whitespace/control characters",
        ),
    ]
    restart = (
        "`unified_sites.country` has no boot-time producer for a curated row: the only writer that "
        "runs at startup is `pipeline/lyra/data_patches.py::fix_countries()`, scoped "
        "`source_id = 'lyra' AND country IS NULL` (orchestrator.py:1062), and "
        "`scripts/audit_enrich.py:560-576` fills `country` only `WHERE country IS NULL`. A written "
        "value therefore survives a restart. `card_stats.civilization` is a copy of `country` "
        "(`api/cardgame/stats.py:184`, upserted by `api/cardgame/generator.py::_upsert_stats`) and is "
        "**not** written here - that generator runs by hand or as a pipeline job, not at API boot; "
        "the divergence this leaves is a named residual in `APPLIED.md` with its check SQL."
    )
    commands = [
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/plan.py --collect",
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/plan.py --write",
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --check-primitive",
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --verify",
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --interests",
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --emit",
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --rehearse",
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --probe-guards",
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --apply",
        "./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical.py -q -rs",
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/mutation_sweep.py",
    ]
    return {
        "set_note": set_note,
        "coverage": coverage,
        "checks": checks,
        "refusal_meaning": refusal_meaning,
        "restart": restart,
        "commands": commands,
        "site_count": len(sites),
        "reviewed": len(reviewed),
    }


if __name__ == "__main__":
    raise SystemExit(main())
