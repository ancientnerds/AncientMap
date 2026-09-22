"""Build the hold list: the rows the hand-read refused, with the reason in one line each.

Owner's rule of 2026-09-21: the first hundred are read by hand. This is that reading, written down -
sixty rows whose OWN reviewer reason does not carry both halves of the claim, or whose evidence is
not checkable at the artefact. Every held row is one the writer would otherwise have written.

    ./.venv/Scripts/python.exe output/remediation/logs/make_holds.py

**The numbers below are line numbers of one exact file**, and the file is regenerable: a re-run of
`write_dry_all.py` after the writer gained a rule (the citation check of 2026-09-22 drops 46 of the
1,074 rows) would move every later line - and a hold keyed by line 88 would then hold some other row
while the row it was written for went through. So the list is pinned to the sequence of change keys it
was read against (`ROWS_KEYS_SHA256`, sha256 over the keys joined by LF, measured on the mass lane's
`ALL_ROWS.jsonl` of 2026-09-22), and a rows file with any other sequence is refused. These holds belong
to the mass lane only; another lane's hand-read is its own list.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - the mass lane's paths and the one JSON-lines reader

ROWS = lanes.lane(lanes.MASS).rows
OUT = lanes.lane(lanes.MASS).apply_root

#: sha256 over the change keys of the rows file the line numbers below were read against, one per
#: line, LF-joined with a trailing LF (1,074 rows, `logs/_write_dry/ALL_ROWS.jsonl`, 2026-09-22).
ROWS_KEYS_SHA256 = "0b7ad95dc6b2ee626d281e31c9a9a2532d0b6ea423acf75ed710be6384ae039b"


def keys_digest(rows: list[dict]) -> str:
    """The digest `ROWS_KEYS_SHA256` is: the rows' change keys in file order, LF-joined."""
    return hashlib.sha256(
        "".join(row["change_key"] + "\n" for row in rows).encode("utf-8")
    ).hexdigest()


def assert_pinned(rows: list[dict]) -> None:
    """Refuse a rows file whose order is not the one the line numbers were written against."""
    digest = keys_digest(rows)
    if digest != ROWS_KEYS_SHA256:
        raise SystemExit(
            f"{ROWS}: its change keys hash to {digest[:16]}, the hold list was read against "
            f"{ROWS_KEYS_SHA256[:16]}. The line numbers would now name other rows; refusing to "
            "write a hold list from them"
        )


#: 1-based line number in ALL_ROWS.jsonl -> the reason it was held.
HOLDS: dict[int, str] = {
    5: "Ein weniger spezifischer Wert (P31 archaeological site) macht den feineren gespeicherten "
    "nicht falsch - so steht es in der Begruendung selbst",
    12: "Vorzeichen-Widerspruch: P571 sagt -0400, der Artikel sagt 400 CE; der Beleg nennt nur den "
    "Eigenschaftsnamen P571, der Wert ist nicht pruefbar",
    22: "Die Begruendung sagt selbst, der Beleg zeige -3000 nicht als falsch",
    26: "Die Begruendung sagt selbst, die gespeicherte Klassifikation sei nicht als falsch gezeigt",
    39: "Ein-Jahres-Verschiebung an einer Bucket-Grenze; kein Datum, und die Begruendung nennt "
    "keinen Beleg fuer -2999",
    61: "Die Begruendung sagt, der Vorschlag sei keine Korrektur eines falschen Typs",
    70: "Der Beleg nennt nur den Eigenschaftsnamen P571 - der Wert -10000 ist nicht pruefbar",
    71: "Die Begruendung sagt selbst, keine der beiden Haelften trage",
    76: "Die Begruendung sagt selbst, der Beleg zeige den gespeicherten Wert nicht als falsch",
    88: "Der Vorschlag Monument wird von den P31-Werten des Objekts selbst widerlegt "
    "(Skulpturengruppe)",
    111: "Die Begruendung sagt, die Belege stuetzten den gespeicherten Wert staerker als den "
    "Vorschlag",
    117: "Kein Beleg fuer einen Bucket-Wechsel (Nutzung ab ~2300 BCE)",
    125: "Die Begruendung sagt selbst, der gespeicherte Wert sei nicht widerlegt",
    128: "'vor ~2000 Jahren' ist ein relatives Alter; der Vorschlag 1 ist damit nicht belegt",
    131: "Der Beleg nennt nur den Eigenschaftsnamen P571 - der Wert ist nicht pruefbar",
    140: "Das Datum betrifft die fruehbronzezeitliche Schicht, nicht den Beginn der Besiedlung",
    141: "Der Vorschlag wird von den Belegen selbst widerlegt (Kulturuebergang, nicht "
    "Siedlungsbeginn)",
    162: "Die Quelle beschreibt Berg und Fundstaette gleichen Namens",
    171: "Die Begruendung sagt, die Belege stuetzten den gespeicherten Wert",
    174: "Beide Werte im gleichen Bucket; die Belege stuetzen einen frueheren Wert als beide",
    176: "20-Jahres-Verschiebung; die Begruendung sagt, der Beleg zeige den gespeicherten Wert "
    "nicht als falsch",
    188: "Die Begruendung sagt, kein Beleg stuetze den vorgeschlagenen Wert -43000",
    192: "Der Beleg nennt nur den Eigenschaftsnamen P571 - der Wert ist nicht pruefbar",
    193: "Das 7. Jh. v. Chr. ist eine Zwischenphase, nicht der frueheste Beginn",
    200: "Bucket-Grenzspiel; kein Beleg fuer einen Bucket-Wechsel",
    202: "Die Begruendung sagt, der Beleg zeige den gespeicherten Sortierschluessel nicht als falsch",
    206: "Bucket-Grenzspiel; die Begruendung sagt, der Vorschlag sei von den Belegen selbst "
    "widerlegt",
    217: "Die Begruendung sagt selbst, der Beleg zeige den gespeicherten Wert nicht als falsch",
    222: "Der Vorschlag Ruin wird von den Belegen widerlegt (erhaltene Synagoge)",
    239: "Der gespeicherte Wert ist feiner als der Vorschlag; beide Haelften fallen laut Begruendung",
    244: "Ein Heiligtum kann einen Tempel enthalten - der gespeicherte Wert ist nicht falsch",
    245: "Der gespeicherte Wert wird von keiner Siedlungsaussage widerlegt",
    246: "'as early as the fifth century' ist kein Gruendungsdatum",
    259: "'Bronze-Age' gibt kein Jahr her; der Vorschlag ist nicht belegt",
    268: "Beide Haelften fallen: der Vorschlag liest das Datum falsch",
    282: "Die Begruendung sagt selbst, der gespeicherte Wert sei nicht widerlegt",
    290: "Eine Nekropole schliesst einen Dolmen ein - der gespeicherte Wert ist nicht falsch",
    303: "Der Vorschlag faellt durch die zweite Haelfte (Göbekli Tepe ist fuer megalithische "
    "Pfeiler bekannt)",
    315: "Die gespeicherte Felsgraeber-Klassifikation ist kein Widerspruch, sondern die feinere "
    "Beschreibung",
    318: "Der gespeicherte Wert ist der feinere Projekt-Bucket, der Vorschlag weniger spezifisch",
    324: "Die Begruendung sagt selbst, der Beleg zeige den gespeicherten Wert nicht als falsch",
    338: "100-Jahres-Verschiebung; die Begruendung sagt, der Beleg zeige den gespeicherten Wert "
    "nicht als falsch",
    345: "Der Huegel traegt den Steinkreis, ist aber selbst kein Steinkreis-Ersatz",
    347: "Beide Werte im gleichen Bucket; 'gegruendet im 6. Jh.' belegt keinen Beginn",
    373: "Der gespeicherte Wert ist feiner und laut Begruendung nicht widerlegt",
    374: "Die Begruendung sagt, der Vorschlag sei willkuerlich gewaehlt (die Quelle nennt kein Jahr)",
    375: "Reine Stiländerung; die Belege stuetzen den gespeicherten Wert",
    391: "BP-Umrechnung: 48.000 BP entspricht ~46.050 v. Chr., der Vorschlag ist also richtig - "
    "aber die Begruendung widerlegt ihn selbst. Von Hand nachlesen.",
    398: "Beide Haelften fallen: der Vorschlag trifft das Ende der belegten Spanne, nicht den Beginn",
    421: "Der Vorschlag Temple complex ist nicht belegt (eine Stoa ist kein Tempel)",
    425: "'had begun by 3100 BCE' ist ein terminus ante quem, kein Beginn",
    430: "Der Beleg nennt nur den Eigenschaftsnamen P571 - der Wert ist nicht pruefbar",
    437: "Die Belege stuetzen beide Lesarten gleich stark - keine Unterscheidung",
    441: "Der gespeicherte Wert ist richtig (ein weisses Pferd ist ein Geoglyph)",
    454: "Der gespeicherte Wert ist richtig (eine roemische Stadt); der Vorschlag ist groeber",
    456: "Die Begruendung sagt, der feinere gespeicherte Typ koenne ebenso gelten",
    458: "Beide Haelften haengen an einer Stilfrage",
    459: "Die Begruendung sagt selbst, nichts zeige den gespeicherten Wert als falsch",
    470: "Die Begruendung sagt, die Belege stuetzten den gespeicherten Wert",
    477: "Der Beleg betrifft die Nutzung, nicht die Errichtung des Bauwerks",
    104: "Der gespeicherte Typ wird von den Grabtuermen (chullpas) gestuetzt; der Vorschlag ist die "
    "groebere Wikidata-Klasse und widerlegt den feineren Wert nicht",
    134: "Der gespeicherte Wert meint die Wallanlage (Ravensburgh Castle), die Quelle beschreibt das "
    "Dorf - der Vorschlag trifft ein anderes Objekt",
    136: "Die Begruendung sagt selbst, sie trage nicht (umstrittenes Gebiet); ohnehin von der "
    "Grenzpruefung abgelehnt",
    148: "Die Begruendung sagt selbst, der gespeicherte Wert sei nicht widerlegt (ein Heiligtum mit "
    "Gasthaeusern und Priesterhaus ist ein Komplex)",
    153: "Die Begruendung sagt selbst, der gespeicherte Bucket sei richtig; der Vorschlag ist eine "
    "Kategorie-Verwechslung",
    167: "Die Begruendung sagt selbst, die Begruendungs-Haelfte falle; der gespeicherte Wert 1 ist der "
    "Sortierschluessel des Buckets 1-500 AD",
    270: "Eine antike Stadt mit sechs Tempeln - der gespeicherte feinere Typ ist nicht falsch, die "
    "groebere Klasse widerlegt ihn nicht",
    349: "Die Begruendung sagt selbst, der gespeicherte Wert sei nicht widerlegt (das Grabmal ist Teil "
    "des groesseren Komplexes)",
    353: "Die Begruendung sagt selbst, der groebere Typ widerlege den feineren Wert nicht - der "
    "gespeicherte Wert bleibt unangetastet",
    376: "Die Begruendung sagt selbst, der gespeicherte Wert passe zur Quelle; der schmalere Vorschlag "
    "macht ihn nicht falsch",
    382: "Die Begruendung sagt, die P31-Werte enthalten Burg UND Wallburg - der gespeicherte Wert ist "
    "nicht widerlegt",
    409: "Der Vorschlag wird von der eigenen Quelle widerlegt, und der gespeicherte Wert ist nicht "
    "widerlegt - keine der beiden Haelften traegt",
}


def main() -> int:
    rows = lanes.read_jsonl(ROWS)
    assert_pinned(rows)
    OUT.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    markdown: list[str] = [
        "| # | Site | Feld | alt | neu | Grund fuer das Zurueckhalten |",
        "|---|---|---|---|---|---|",
    ]
    for number in sorted(HOLDS):
        row = rows[number - 1]
        reason = HOLDS[number]
        records.append(
            {
                "number": number,
                "change_key": row["change_key"],
                "site_id": row["site_id"],
                "site_name": row["site_name"],
                "column": row["column"],
                "old_value": row["old_value"],
                "new_value": row["new_value"],
                "hold_reason": reason,
            }
        )
        markdown.append(
            f"| {number} | {row['site_name']} | {row['column']} | `{row['old_value']}` | "
            f"`{row['new_value']}` | {reason} |"
        )

    (OUT / "HOLDS.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    text = (
        "# Zurueckgehaltene Zeilen der Handpruefung (2026-09-21)\n\n"
        f"{len(records)} von {len(rows)} geplanten Zeilen. Jede Zeile traegt in ihrem eigenen\n"
        "Pruefer-Verdikt eine Begruendung, die den Vorschlag nicht stuetzt (oder einen Beleg, der\n"
        "den Wert nicht zeigt). Sie werden NICHT geschrieben; sie stehen in der Tabelle fuer Martin.\n\n"
        + "\n".join(markdown)
        + "\n"
    )
    (OUT / "HOLDS.md").write_text(text, encoding="utf-8")
    print(f"{len(records)} Zurueckhaltungen geschrieben nach {OUT / 'HOLDS.jsonl'} und HOLDS.md")
    for record in records:
        print(
            f"{record['number']:3} {record['site_name'][:30]:31} {record['column']:12} {record['hold_reason'][:60]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
