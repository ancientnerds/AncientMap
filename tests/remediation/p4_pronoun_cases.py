"""The sentences both sides must judge alike under pilot 3's pronoun rule (T1 and T4).

V6 held a published sentence only when it *opened* with a word of `model4.PRONOUN_OPENERS` and its
source predecessor was not published right before it; V10 held a card item only when it opened with
one. Pilot 3's audit found two pronouns that depend on the source sentence before them all the same,
one past the first word each: Stanydale Temple, "Pottery sherds show that it was also occupied in
the late Bronze Age ..." (in the source, *it* is the settlement of the sentence before; the review
dropped that sentence), and Dolebury Warren's card, "Standing on a limestone ridge on the northern
edge of the Mendip Hills, it was made into a hill fort ..." (the card never names what *it* is).

The rule, measured over the census pools and pilots 1-3's published texts (AUDIT_LOG, pilot 4): a
sentence also leans on the sentence before it in its source when its first word of
`model4.PERSONAL_PRONOUNS` (whole, any case) is a word of `model4.SUBJECT_PRONOUNS` and stands right
after the sentence's first comma (`, `), or right after the word `that` with no word of
`model4.ARTICLES` before it. `verify4.leaning_pronoun` (V6, V10) and `sentences.leans_on_predecessor`
(the review's drops, T8) each implement it in their own code; a parity test runs both over these
texts. The selector is told the rule as its rule (10).
"""

from __future__ import annotations

#: `(text, leans)`: does the sentence lean on the sentence before it in its source?
PRONOUN_CASES: list[tuple[str, bool]] = [
    # pilot 3's two cases
    (
        "Pottery sherds show that it was also occupied in the late Bronze Age (1000–700 BC) and "
        "early Iron Age (600–400 BC).",
        True,
    ),
    (
        "Standing on a limestone ridge on the northern edge of the Mendip Hills, it was made into a "
        "hill fort during the Iron Age and was occupied into the Roman period.",
        True,
    ),
    # V6's opener list, as before
    ("It is located on cliffs above the Danube.", True),
    ("Its ruins lie near the modern town.", True),
    ("The latter was built later.", True),
    ("Here the expedition found a lot of sculptures.", True),
    ("Thereafter the fort was used as a quarry.", False),
    ("Items were found in the lower layers.", False),
    # a subject pronoun right after the first comma
    ("Oval in form, it is the second-largest Neolithic mound in Britain.", True),
    ("Outside of the Bible, it was mentioned by Ptolemy and Pliny.", True),
    ("In 1882, he investigated the passage grave and found amber beads.", True),
    ("After many years of use, they were abandoned because of cracks.", True),
    ("In 4,500 BC, she was buried with a necklace of amber beads.", True),
    # ... but not after a later comma, nor when a personal pronoun came first
    ("The fort was abandoned, and later it was used as a quarry.", False),
    (
        "The first buildings date from AD 70 to 110, and in the 2nd century, they were replaced in "
        "stone.",
        False,
    ),
    (
        "After its destruction during the Dacian War, it was rebuilt in 100 AD with stone walls.",
        False,
    ),
    ("During the 12th century, the arch contained the home of a noble family.", False),
    # a subject pronoun right after 'that', no article before it
    ("Some believe that it always was recumbent.", True),
    ("Radiocarbon dating shows that it was occupied from 3800 BC to 2800 BC.", True),
    ("That it was a temple is shown by the altar found inside.", True),
    ("Experts believe that they were built during the Iron Age.", True),
    # ... not with an article before it: the sentence names what it may refer to
    ("The wide chronology of the city shows that it became a permanent settlement.", False),
    ("Finds from the site suggest that it was mainly occupied in the 1st century AD.", False),
    (
        "The period of the camp's construction is unclear, but it has been suggested that it may "
        "lie in the 2nd century BC.",
        False,
    ),
    # a subject pronoun elsewhere is not the rule's: its antecedent is usually in the sentence
    (
        "The temple is 66 m long and 35 m wide, making it only slightly smaller than the Temple "
        "of Jupiter.",
        False,
    ),
    (
        "The earliest version of the fort was probably founded around AD 80 and it was occupied.",
        False,
    ),
    ("Visitors can reach it by bus from the village.", False),
    # a word is whole: no pronoun inside another word, and a contraction is no pronoun of the list
    ("Overall, item after item was found in the pit below the wall.", False),
    ("On the hill, its walls still stand to a height of two metres.", False),
    ("On the hill, it's said that the walls still stand.", False),
    ("Thatcher showed that items were found in the pit below the wall.", False),
]
