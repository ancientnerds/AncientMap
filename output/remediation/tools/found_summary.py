"""Zaehlt, was der Massenlauf bisher gefunden hat - rein lesend aus den Stapelberichten.

Grund: Martin will wissen, welche Fehler in der Datenbank bisher gefunden und behoben wurden.
Kein Netz, keine Datenbank, kein Schreibzugriff: nur die Dateien der bereits gerechneten Stapel.
Ein Stapel, der gerade geschrieben wird, kann zerrissen sein - solche Dateien werden gezaehlt und
uebersprungen, nicht stillschweigend als leer behandelt.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - die Pfade der Spur (Standard: der Massenlauf)


def load(path: pathlib.Path) -> dict | None:
    """Liest eine JSON-Datei; None heisst 'nicht lesbar' (fehlend, zerrissen oder kein Objekt)."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def value_counts(items: list[dict], field: str, limit: int = 12) -> str:
    """Verteilung der Werte eines Feldes, kompakt."""
    counts = collections.Counter(str(i.get(field)) for i in items)
    return ", ".join(f"{k} {v}" for k, v in counts.most_common(limit))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="found-summary")
    parser.add_argument("--lane", default=lanes.MASS, help="which run's paths (lanes.py)")
    run = lanes.lane(parser.parse_args(argv).lane).run_dir
    batches = sorted(p for p in run.iterdir() if p.is_dir() and (p / "input.json").exists())
    models: dict[str, dict] = {}
    reviews: dict[str, dict] = {}
    torn: list[str] = []

    for batch in batches:
        model = load(batch / "model.json")
        if model is None:
            if (batch / "model.json").exists():
                torn.append(batch.name)
        else:
            models[batch.name] = model
        review = load(batch / "review.json")
        if review is not None:
            reviews[batch.name] = review

    print(
        f"Stapel: {len(batches)} | Modellbericht: {len(models)} | Pruefbericht: {len(reviews)}"
        f" | zerrissen: {len(torn)}"
    )
    if torn:
        print("  zerrissen:", ", ".join(torn[:5]))

    judgements = [j for m in models.values() for j in m.get("judgements", [])]
    sites = {
        s if isinstance(s, str) else (s.get("site_id") or s.get("id"))
        for m in models.values()
        for s in m.get("sites", [])
    }
    sites.discard(None)

    print(f"\nBewertungen (ein Eintrag = ein Feld einer Site): {len(judgements)}")
    print(f"Sites im Lauf: {len(sites)}")

    if judgements:
        print("  Felder einer Bewertung:", sorted(judgements[0].keys()))
        print("  Beispiel:", json.dumps(judgements[0], ensure_ascii=False)[:400])
        for field in sorted(judgements[0].keys()):
            values = {str(j.get(field)) for j in judgements}
            if len(values) <= 12:
                print(f"  {field}: {value_counts(judgements, field)}")

    print(
        f"\nKosten laut Berichten: {sum(m.get('totals', {}).get('calls', 0) for m in models.values())} Aufrufe"
    )

    if reviews:
        sample = next(iter(reviews.values()))
        print("\nSchluessel im Pruefbericht:", sorted(sample.keys())[:20])
        entries = sample.get("reviews") or sample.get("verdicts") or []
        if entries:
            print("  Felder eines Pruefurteils:", sorted(entries[0].keys()))
            print("  Beispiel:", json.dumps(entries[0], ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
