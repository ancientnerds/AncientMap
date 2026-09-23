"""The span cases both span finders must agree on (PHASE4_CONTRACTS.md section 7, decision D3).

`sentences.split_source` (S2, the selection) and verify4's own candidate-span finder (V4, the
independent check) implement the same rules and neither imports the other. Each case is a
one-sentence text and exactly the spans it offers, `span id -> the text of its range`. The texts
are written for the tests; one covers each rule and each refusal of section 7. A parity test runs
both finders over these texts and asserts the same span sets.
"""

from __future__ import annotations

#: `(source id, text, {span id: range text})`.
SPAN_CASES: list[tuple[str, str, dict[str, str]]] = [
    ("W", "A second shrine (the south shrine) was added later.", {"p1": " (the south shrine)"}),
    ("W", "(Built in stone) The shrine was added later on the hill.", {"p1": "(Built in stone) "}),
    ("W", "The shrine(s) stood on the hill above the old ford.", {"p1": "(s)"}),
    (
        "W",
        "The temple, which stood on a low ridge, was used for a thousand years.",
        {
            "l1": "The temple, ",
            "a1": ", which stood on a low ridge,",
            "t1": ", was used for a thousand years",
        },
    ),
    (
        "W",
        "About 4,500 people lived in the town, which lay on the river.",
        {"t1": ", which lay on the river"},
    ),
    ("W", "The temple (built, as some say, by giants) stands on the hill above.", {}),
    (
        "W",
        "The site lies 2 km south of the village – near the old road – on farmland.",
        {"a1": " – near the old road –"},
    ),
    (
        "W",
        "The corridor – lined with limestone – rises gently – lined with granite – to its end.",
        {"a1": " – lined with limestone –", "a2": " – lined with granite –"},
    ),
    ("W", "The fort lay on the road from Boulogne – Cologne and Xanten – Aachen – Trier.", {}),
    (
        "W",
        "In the period from 1800 – 500 BC, 100 – 150 burial mounds were built every year.",
        {"t1": ", 100 – 150 burial mounds were built every year"},
    ),
    (
        "W",
        "The mound – fully 12 m across – stands on the ridge above the ford.",
        {"a1": " – fully 12 m across –"},
    ),
    ("W", "The mound – 12 m across – stands on the ridge above the ford.", {}),
    ("W", "The wall was built in 1200 – of local stone – on the ridge above.", {}),
    ("W", "The beads are long – barrel-shaped; the pendants – round and flat.", {}),
    (
        "W",
        "The corridor – lined with slabs (granite; basalt) – rises to its end.",
        {"a1": " – lined with slabs (granite; basalt) –", "p1": " (granite; basalt)"},
    ),
    ("W", "The temple—the largest of its kind—stood on the hill above.", {}),
    (
        "W",
        "The temples of Asclepius, Aphrodite, Apollo, and Artemis stood on the hill.",
        {"l1": "The temples of Asclepius, ", "t1": ", and Artemis stood on the hill"},
    ),
    (
        "W",
        "The temple held statues of the goddess of the harvest, the god of the sea, and the god of war.",
        {"t1": ", and the god of war"},
    ),
    (
        "W",
        "Finds from the ditch included pottery, coins, tools and bones from the pit.",
        {"l1": "Finds from the ditch included pottery, ", "t1": ", tools and bones from the pit"},
    ),
    (
        "W",
        "It lies in the provinces of Nevsehir, Kayseri, Aksaray, Kirsehir, Sivas and Nigde.",
        {"t1": ", Sivas and Nigde"},
    ),
    (
        "W",
        "The coins were minted under the rule of Constantine I, Theodosius I, Tiberius Nero.",
        {"t1": ", Tiberius Nero"},
    ),
    ("W", "The hill fort lies near the village of Clovelly, Devon, England.", {"t1": ", England"}),
    (
        "W",
        "The temple, now ruined, held statues of the gods of the river and of the sky.",
        {
            "l1": "The temple, ",
            "a1": ", now ruined,",
            "t1": ", held statues of the gods of the river and of the sky",
        },
    ),
    (
        "W",
        "In 1900, the site was cleared of rubble by the governor.",
        {"l1": "In 1900, ", "t1": ", the site was cleared of rubble by the governor"},
    ),
    (
        "W",
        "In the first year of the war, the site was cleared by the army.",
        {"t1": ", the site was cleared by the army"},
    ),
    (
        "W",
        "The temple was built by a farming community, whose tombs lie nearby.",
        {"t1": ", whose tombs lie nearby"},
    ),
    (
        "W",
        "The temple, probably built by farmers, was used for many centuries.",
        {"l1": "The temple, ", "t1": ", was used for many centuries"},
    ),
    (
        "W",
        "Presumably, the dead were first laid down in the open on the hill.",
        {"t1": ", the dead were first laid down in the open on the hill"},
    ),
    (
        "W",
        "The cave yielded, arguably, the oldest bison bones in the region.",
        {"l1": "The cave yielded, ", "t1": ", the oldest bison bones in the region"},
    ),
    (
        "W",
        "They don't have any drilled holes, which shows the talons were worn loose.",
        {"t1": ", which shows the talons were worn loose"},
    ),
    (
        "W",
        "The finds, which oughtn't be moved, lie in the museum of the town.",
        {"l1": "The finds, ", "t1": ", lie in the museum of the town"},
    ),
    (
        "W",
        "The shrine was abandoned, as the deity venerated there cannot be named.",
        {"l1": "The shrine was abandoned, "},
    ),
    (
        "W",
        "The mound, which won’t yield to the plough, rises above the field.",
        {"l1": "The mound, ", "t1": ", rises above the field"},
    ),
    (
        "W",
        "The temple was built c. 2500 BC by a farming community, whose tombs lie nearby.",
        {"t1": ", whose tombs lie nearby"},
    ),
    ("W", "In 1900, the shrine) was added (later, on the hill top.", {}),
    ("W", "The temple, which stood on a low ridge, was used for a thousand years", {}),
    # a translated sentence offers no span (the protected tokens are English)
    ("T.fr", "Le temple fut bâti par des paysans, ce qui n'est cependant pas prouvé.", {}),
    ("T.de", "Der Tempel wurde, vermutlich, von Bauern auf dem Hügel errichtet.", {}),
]
