"""The sentences both sides must judge alike under pilot 2's two well-formedness rules (T5).

Pilot 2's audit found two garbles copied word for word from their sources and published: Bassae,
"... on the slopes of Cotylion Mountain. near the village of Skliros, ..." (a full stop inside the
sentence before a lowercase word: the shared splitter never splits there), and Vindobala, "... and in
the hamlet of, Rudchester, Northumberland." (a preposition directly before a comma). V5 holds a
published sentence that carries either (`verify4.ill_formed`), and S2's pool offers no sentence that
does (`sentences.garbled`), each in its own code (the D3 idea, PHASE4_CONTRACTS.md section 7). A
parity test runs both over these texts.

The full-stop rule spares the stop that ends an initialism or a single letter - `B.C. and`, `i.e.
the`, `e.g. near`, `c. 500` is no lowercase word anyway - because that stop ends no sentence. The
prepositions are the closed list that takes an object and stands as no adverb: `later on,` and
`inside,` are fine English and are not in it.
"""

from __future__ import annotations

#: `(text, garbled)`.
GARBLE_CASES: list[tuple[str, bool]] = [
    # Bassae W, pilot 2: the source's own typo
    (
        "Bassae lies at an elevation of 1,131 m above sea level on the slopes of Cotylion "
        "Mountain. near the village of Skliros, northeast of Figaleia.",
        True,
    ),
    ("It may have been the first amphitheatre built by the Romans. and was used for games.", True),
    ("The fort was abandoned in the third century AD. which destroyed the roof.", True),
    ("The work is listed in Cambridge University Press. p.", True),
    ("Englehardt et al. made an effort to establish the origin of the block.", True),
    ("Coins, vases etc. have also been discovered on the hill above the town.", True),
    # the stop of an initialism or of a single letter ends no sentence
    ("The island was first settled in the 7th century B.C. and was abandoned later.", False),
    ("It was built using spolia, i.e. material from earlier buildings nearby.", False),
    ("It was built using spolia (i.e. material from earlier buildings) nearby.", False),
    ("The excavation was led by A. Coelho and F. da Silva in the summer of 1960.", False),
    ("The wall was found in 1960 (F. da Silva excavated the site) near the tower.", False),
    ("The ditch is 22 m. deep at the north end of the rampart on the hill.", False),
    ("The ferry runs between 9 a.m. and 2 p.m. daily except on Mondays.", False),
    # a stop before a capital or a digit is no garble of this kind
    ("The temple stood on the hill. It was rebuilt later on the same plan.", False),
    ("The cave was used c. 500 BC by herders from the valley below it.", False),
    # Vindobala W, pilot 2: the source's own typo
    (
        "Vindobala was a Roman fort with the modern name, and in the hamlet of, Rudchester, "
        "Northumberland.",
        True,
    ),
    # a preposition stranded in a coordination is fine English and is held too (decision D7,
    # safety over coverage): 66 of the census's 89,072 pool sentences carry the pattern at all
    ("The fort lies 1 km west of, and within sight of, the town of Cierium.", True),
    ("The finds were taken to, and kept in, the museum of the town.", True),
    ("The cave was used until, in 1951, it was excavated by the museum.", True),
    # adverbs and particles before a comma stand in no list
    ("Later on, the site was excavated by a team from the university.", False),
    ("Inside, the chamber was lined with slabs of local sandstone.", False),
    ("The walls were built over, and the ditch was filled in, by the farmers.", False),
    # a list or a name, not a preposition
    ("The groups A, B and C lie outside the walls of the city of Mixco.", False),
    ("It is located in Xi'an, Shaanxi, in the north-west of the country.", False),
    ("Many of the finds are kept in period VIa, beside the fort's granary.", False),
    # a whole word only: the end of a longer word is no preposition
    ("The site is known from an old photo, taken in 1890 by the vicar.", False),
    ("The hut was a lean-to, built against the north wall of the fort.", False),
]
