"""
Tests for Melbourne data loading and spatial analysis.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np


class TestDataLoading:
    """Test the Melbourne Open Data loading functions."""

    def test_pedestrian_data_has_required_columns(self):
        from smart_street_lighting.data.load_melbourne_data import load_pedestrian_data
        df = load_pedestrian_data(limit=500)
        required = ["sensor_name", "pedestriancount", "Latitude", "Longitude"]
        for col in required:
            assert col in df.columns, f"Missing column: {col}"

    def test_pedestrian_data_coordinates_valid(self):
        from smart_street_lighting.data.load_melbourne_data import load_pedestrian_data
        df = load_pedestrian_data(limit=500)
        valid = df.dropna(subset=["Latitude", "Longitude"])
        assert len(valid) > 0, "No valid coordinates"
        # Melbourne bounding box
        assert valid["Latitude"].between(-38.5, -37.5).all(), "Latitude out of Melbourne range"
        assert valid["Longitude"].between(144.5, 145.5).all(), "Longitude out of Melbourne range"

    def test_streetlight_data_has_lux(self):
        from smart_street_lighting.data.load_melbourne_data import load_streetlight_data
        df = load_streetlight_data(limit=500)
        assert "lux_level" in df.columns
        assert df["lux_level"].notna().sum() > 0

    def test_streetlight_lux_values_reasonable(self):
        from smart_street_lighting.data.load_melbourne_data import load_streetlight_data
        df = load_streetlight_data(limit=500)
        lux = df["lux_level"].dropna()
        assert lux.min() >= 0, "Negative lux values"
        assert lux.max() < 200, "Unreasonably high lux values"

    def test_sensor_summary(self):
        from smart_street_lighting.data.load_melbourne_data import load_pedestrian_data, get_sensor_summary
        df = load_pedestrian_data(limit=500)
        summary = get_sensor_summary(df)
        assert "sensor_name" in summary.columns
        assert "avg_hourly_traffic" in summary.columns
        assert len(summary) > 0



# NOTE: TestSpatialAnalysis and TestTemporalAnalysis were removed in v0.2.0
# when the spatial_analysis and temporal_analysis modules moved out of the
# plugin into the submission notebook. The notebook now exercises that
# code inline, with the assertions made directly against the results.
