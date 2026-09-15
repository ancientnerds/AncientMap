"""Country phrases must be whole names, not fragments of longer ones.

Found on the first real paper (2026-09-15): the model returned "Mexico" as
the country for a paragraph that says "highland New Mexico", and the
verbatim check accepted it because "Mexico" is a substring of "New Mexico".
For gating, only a phrase that normalize_country() maps to a real country
may count; a state or region name stays visible on the card but never
drives the country gate.
"""

from pipeline.lyra.prospector import gate_country
from pipeline.lyra.prospector.mentions import _verbatim_in


class TestVerbatimCountry:
    def test_fragment_of_a_longer_capitalised_name_is_rejected(self):
        assert (
            _verbatim_in("Pithouses of highland New Mexico were dug.", "Mexico", country=True)
            is None
        )
        assert _verbatim_in("Farms in South Africa.", "Africa", country=True) is None
        assert _verbatim_in("Finds from Papua New Guinea.", "Guinea", country=True) is None

    def test_whole_country_name_is_accepted(self):
        assert (
            _verbatim_in("Temples of ancient Egypt were rebuilt.", "Egypt", country=True) == "Egypt"
        )
        assert _verbatim_in("Egypt. The Nile floods.", "Egypt", country=True) == "Egypt"
        assert (
            _verbatim_in("Sites in New Mexico and Arizona.", "New Mexico", country=True)
            == "New Mexico"
        )

    def test_word_boundary_is_required(self):
        assert _verbatim_in("The Omani coast.", "Oman", country=True) is None

    def test_period_phrases_keep_the_plain_rule(self):
        assert (
            _verbatim_in("dated to cal AD 895–990 by Mauldin.", "cal AD 895–990")
            == "cal AD 895–990"
        )


class TestGateCountry:
    def test_real_country_from_text_is_used_for_gating(self):
        assert gate_country(None, "Egypt") == "Egypt"

    def test_state_or_region_from_text_is_not_used_for_gating(self):
        assert gate_country(None, "New Mexico") is None
        assert gate_country(None, "Catron County, New Mexico") is None

    def test_resolved_country_always_wins(self):
        assert gate_country("United States", "New Mexico") == "United States"


class TestDesignationDates:
    def test_monument_inception_is_not_an_occupation_date(self, monkeypatch):
        from pipeline.lyra.prospector import resolve

        monkeypatch.setattr(
            resolve,
            "_fetch_qid_labels",
            lambda qids: {"Q1201275": "national monument of the United States"},
        )
        assert resolve._is_designation(["Q1201275"]) is True

    def test_archaeological_site_class_is_a_real_period_carrier(self, monkeypatch):
        from pipeline.lyra.prospector import resolve

        monkeypatch.setattr(
            resolve, "_fetch_qid_labels", lambda qids: {"Q839954": "archaeological site"}
        )
        assert resolve._is_designation(["Q839954"]) is False

    def test_empty_p31_is_not_a_designation(self):
        from pipeline.lyra.prospector import resolve

        assert resolve._is_designation([]) is False
