"""
Tests for crime data loading and LGA lookups.

The risk-scoring formula and P-category adjustment moved out of the
plugin in v0.2.0 (they now live transparently in the submission
notebook). The plugin keeps only the I/O surface tested here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from smart_street_lighting.data.safety_analysis import (
    load_crime_data,
    get_lga_for_location,
    get_lga_with_fallback_info,
)


# ============================================================
# Crime data loading
# ============================================================

class TestCrimeDataLoading:
    def test_load_returns_dataframe(self):
        df = load_crime_data()
        assert not df.empty
        assert "lga_name" in df.columns
        assert "rate_per_100k" in df.columns

    def test_filters_relevant_offences(self):
        df = load_crime_data()
        valid = {"Assault", "Robbery", "Property Damage", "Stalking"}
        assert set(df["offence_category"].unique()).issubset(valid)


# ============================================================
# LGA lookup
# ============================================================

class TestLGALookup:
    def test_fitzroy_gardens(self):
        assert get_lga_for_location("Fitzroy Gardens") == "Melbourne"

    def test_edinburgh_gardens(self):
        assert get_lga_for_location("Edinburgh Gardens") == "Yarra"

    def test_unknown_defaults_to_melbourne(self):
        assert get_lga_for_location("Some Unknown Park") == "Melbourne"

    def test_case_insensitive(self):
        assert get_lga_for_location("FITZROY GARDENS") == "Melbourne"


# ============================================================
# Fallback surfacing (S5-02 / item 11)
# ============================================================

class TestFallbackSurfacing:
    """Silent fallbacks must surface fallback_used + fallback_reason."""

    def test_known_location_no_fallback(self):
        info = get_lga_with_fallback_info("Fitzroy Gardens")
        assert info["fallback_used"] is False
        assert info["lga_name"] == "Melbourne"

    def test_unknown_location_marks_fallback(self):
        info = get_lga_with_fallback_info("Some Unknown Park")
        assert info["fallback_used"] is True
        assert "Melbourne" in info["lga_name"]
        assert "PARK_LGA_MAP" in info["fallback_reason"]

    def test_get_lga_for_location_backcompat(self):
        assert isinstance(get_lga_for_location("Fitzroy Gardens"), str)
        assert get_lga_for_location("Some Unknown Park") == "Melbourne"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
