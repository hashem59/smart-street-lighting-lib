"""
Unit tests for the AS/NZS 1158 lighting calculation engine.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import pytest
from smart_street_lighting.llm.calculation_engine import (
    design_lighting,
    select_p_category,
    select_led_spec,
    calculate_spacing,
    select_pole_height,
    P_CATEGORIES,
    OPERATING_HOURS_PER_YEAR,
    ELECTRICITY_RATE_PER_KWH,
    CARBON_FACTOR_VIC_SCOPE2_3,
    LED_LIFESPAN_YEARS,
    LED_MAINTENANCE_FACTOR,
    HPS_LIFESPAN_YEARS,
)


# ============================================================
# P-Category Selection
# ============================================================

class TestCategorySelection:
    def test_park_path_low(self):
        assert select_p_category("low", "park_path") == "P10"

    def test_park_path_moderate(self):
        assert select_p_category("moderate", "park_path") == "P9"

    def test_park_path_high(self):
        assert select_p_category("high", "park_path") == "P3"

    def test_park_path_very_high(self):
        assert select_p_category("very_high", "park_path") == "P2"

    def test_shared_path_high(self):
        assert select_p_category("high", "shared_path") == "P2"

    def test_residential_low(self):
        assert select_p_category("low", "residential") == "P8"

    def test_all_categories_exist(self):
        for level in ["low", "moderate", "high", "very_high"]:
            for loc_type in ["park_path", "shared_path", "public_space", "residential"]:
                cat = select_p_category(level, loc_type)
                assert cat in P_CATEGORIES, f"{cat} not in P_CATEGORIES"


# ============================================================
# Spacing and Pole Height
# ============================================================

class TestSpacingAndPoleHeight:
    def test_spacing_within_range(self):
        """Spacing should be 3-5x pole height per AS/NZS 1158."""
        for cat_id in P_CATEGORIES:
            height = select_pole_height(cat_id, 3.0)
            spacing = calculate_spacing(height, cat_id)
            ratio = spacing / height
            assert 3.0 <= ratio <= 5.0, f"{cat_id}: ratio {ratio} outside 3-5x range"

    def test_higher_categories_have_closer_spacing(self):
        """P1 should have closer spacing than P10 for same pole height."""
        sp_p1 = calculate_spacing(5.0, "P1")
        sp_p10 = calculate_spacing(5.0, "P10")
        assert sp_p1 < sp_p10

    def test_pole_height_minimum(self):
        for cat_id in P_CATEGORIES:
            height = select_pole_height(cat_id, 2.0)
            assert height >= 3.5, f"{cat_id}: pole height {height}m too low"


# ============================================================
# Light Count (Fence-Post Formula)
# ============================================================

class TestLightCount:
    def test_200m_path_p9(self):
        d = design_lighting("Test", 200, 3.0, "moderate", "park_path")
        # P9: pole 4m, spacing 16m -> floor(200/16)+1 = 13
        assert d.num_lights == 13

    def test_200m_path_p3(self):
        d = design_lighting("Test", 200, 3.0, "high", "park_path")
        # P3: pole 5m, spacing 17.5m -> floor(200/17.5)+1 = 12
        assert d.num_lights == 12

    def test_minimum_2_lights(self):
        d = design_lighting("Short", 5, 2.0, "low", "park_path")
        assert d.num_lights >= 2

    def test_longer_path_more_lights(self):
        d1 = design_lighting("Short", 100, 3.0, "moderate", "park_path")
        d2 = design_lighting("Long", 500, 3.0, "moderate", "park_path")
        assert d2.num_lights > d1.num_lights


# ============================================================
# Energy Calculations
# ============================================================

class TestEnergyCalculations:
    def test_energy_formula(self):
        d = design_lighting("Test", 200, 3.0, "moderate", "park_path")
        expected_kwh = (d.num_lights * d.led_wattage * OPERATING_HOURS_PER_YEAR) / 1000
        assert abs(d.annual_energy_kwh - expected_kwh) < 0.01

    def test_cost_formula(self):
        d = design_lighting("Test", 200, 3.0, "moderate", "park_path")
        expected_cost = d.annual_energy_kwh * ELECTRICITY_RATE_PER_KWH
        assert abs(d.annual_energy_cost_aud - expected_cost) < 0.01

    def test_co2_formula(self):
        d = design_lighting("Test", 200, 3.0, "moderate", "park_path")
        expected_co2 = d.annual_energy_kwh * CARBON_FACTOR_VIC_SCOPE2_3
        assert abs(d.annual_co2_kg - expected_co2) < 0.01

    def test_led_cheaper_than_hps(self):
        d = design_lighting("Test", 200, 3.0, "moderate", "park_path")
        assert d.annual_energy_cost_aud < d.hps_annual_cost_aud

    def test_energy_saving_positive(self):
        d = design_lighting("Test", 200, 3.0, "moderate", "park_path")
        assert d.energy_saving_percent > 0

    def test_energy_saving_range(self):
        """LED should save 50-70% vs HPS."""
        d = design_lighting("Test", 200, 3.0, "high", "park_path")
        assert 50 <= d.energy_saving_percent <= 75


# ============================================================
# Activity Level from Pedestrian Count
# ============================================================

class TestActivityLevelOverride:
    def test_low_traffic(self):
        d = design_lighting("Test", 200, 3.0, avg_pedestrian_count=30)
        assert d.activity_level == "low"

    def test_moderate_traffic(self):
        d = design_lighting("Test", 200, 3.0, avg_pedestrian_count=150)
        assert d.activity_level == "moderate"

    def test_high_traffic(self):
        d = design_lighting("Test", 200, 3.0, avg_pedestrian_count=500)
        assert d.activity_level == "high"

    def test_very_high_traffic(self):
        d = design_lighting("Test", 200, 3.0, avg_pedestrian_count=1500)
        assert d.activity_level == "very_high"


# ============================================================
# Payback Period
# ============================================================

class TestPayback:
    def test_payback_positive(self):
        d = design_lighting("Test", 200, 3.0, "moderate", "park_path")
        assert d.payback_years > 0

    def test_payback_reasonable(self):
        """Payback should be within 3-30 years for realistic scenarios."""
        d = design_lighting("Test", 200, 3.0, "high", "park_path")
        assert 3 <= d.payback_years <= 30




# ============================================================
# Photometric verification (S4-02 / backlog 01)
# ============================================================

from smart_street_lighting.llm.calculation_engine import verify_design, LightingDesign


class TestPhotometricVerification:
    """Back-check that designed layouts actually deliver the required lux."""

    def test_dense_p10_layout_passes(self):
        """A deliberately dense P10 layout (8m spacing, 30W LED) should
        clear the conservative cosine-cubed verification with margin."""
        d = LightingDesign(
            location_name="dense-p10",
            pathway_length_m=50,
            pathway_width_m=3.0,
            activity_level="low",
        )
        d.p_category = "P10"
        d.required_avg_lux = 1.0
        d.required_min_lux = 0.5
        d.required_uniformity = 0.5
        d.pole_height_m = 4.0
        d.spacing_m = 8.0
        d.num_lights = 7
        d.led_wattage = 30
        d.led_lumens = 4500
        v = verify_design(d)
        assert v["compliant"] is True, (
            f"Expected compliant; got deficits={v['deficits']}"
        )
        assert v["achieved_avg_lux"] >= d.required_avg_lux
        assert v["achieved_min_lux"] >= d.required_min_lux
        assert v["achieved_uniformity"] >= d.required_uniformity

    def test_underpowered_p3_layout_fails(self):
        """A P3 (moderate-pedestrian, 7 lux required) with 30W LEDs and
        30m spacing must fail — the lumens are too low."""
        d = LightingDesign(
            location_name="bad-p3",
            pathway_length_m=200,
            pathway_width_m=3.0,
            activity_level="high",
        )
        d.p_category = "P3"
        d.required_avg_lux = 7.0
        d.required_min_lux = 3.5
        d.required_uniformity = 0.5
        d.pole_height_m = 4.0
        d.spacing_m = 30.0
        d.num_lights = 7
        d.led_wattage = 30
        d.led_lumens = 4500
        v = verify_design(d)
        assert v["compliant"] is False
        assert v["deficits"]["avg_lux_deficit"] > 0
        assert v["deficits"]["min_lux_deficit"] > 0

    def test_design_verify_method(self):
        """LightingDesign.verify() populates the verification field."""
        d = design_lighting("park-low", 60, 3.0, "low", "park_path")
        result = d.verify()
        assert d.verification == result
        assert "compliant" in result
        assert "deficits" in result
        assert "maintenance_factor" in result

    def test_maintenance_factor_applied(self):
        """Passing maintenance_factor=1.0 (initial) must produce a higher
        avg than the default (0.87 maintained)."""
        d = design_lighting("park-mod", 50, 3.0, "moderate", "park_path")
        v_maint = verify_design(d, maintenance_factor=0.87)
        v_init = verify_design(d, maintenance_factor=1.0)
        assert v_init["achieved_avg_lux"] > v_maint["achieved_avg_lux"]
        # Ratio should be close to 1/0.87
        assert abs(v_init["achieved_avg_lux"] / v_maint["achieved_avg_lux"] - (1/0.87)) < 0.01




# ============================================================
# Lifecycle / maintenance integration (S4-03 / backlog 02)
# ============================================================

class TestLifecycleIntegration:
    """LED_MAINTENANCE_FACTOR and LED_LIFESPAN_YEARS now drive lifecycle calcs."""

    def test_lifecycle_fields_populated(self):
        d = design_lighting("life-test", 100, 3.0, "moderate", "park_path")
        assert d.lifetime_energy_kwh > 0
        assert abs(d.lifetime_energy_kwh - d.annual_energy_kwh * LED_LIFESPAN_YEARS) < 1e-6
        assert d.lifetime_energy_cost_aud > 0
        assert d.lifetime_co2_kg > 0

    def test_hps_replacements_within_horizon(self):
        d = design_lighting("life-test", 100, 3.0, "moderate", "park_path")
        # 20-yr LED life with 4-yr HPS life => 5 replacements
        assert d.hps_lifetime_replacements == LED_LIFESPAN_YEARS // HPS_LIFESPAN_YEARS

    def test_lifecycle_savings_positive(self):
        """Over the LED lifespan, the LED design should be cheaper than the
        HPS baseline (energy + replacement + maintenance)."""
        d = design_lighting("life-test", 200, 3.0, "high", "park_path")
        assert d.lifecycle_savings_aud > 0

    def test_maintained_lumen_target_set(self):
        """maintained_avg_lux_target = required_avg / MF."""
        d = design_lighting("life-test", 100, 3.0, "moderate", "park_path")
        expected = d.required_avg_lux / LED_MAINTENANCE_FACTOR
        assert abs(d.maintained_avg_lux_target - expected) < 0.01

    def test_lifecycle_summary_returns_nested_dict(self):
        d = design_lighting("life-test", 100, 3.0, "moderate", "park_path")
        s = d.lifecycle_summary()
        assert "led_lifetime" in s
        assert "hps_lifetime" in s
        assert s["led_lifetime"]["energy_kwh"] == round(d.lifetime_energy_kwh, 1)
        assert s["hps_lifetime"]["replacements"] == d.hps_lifetime_replacements




# ============================================================
# Solar-PV alternative (S5-08 / backlog 03)
# ============================================================

from smart_street_lighting.llm.calculation_engine import size_solar_alternative


class TestSolarAlternative:
    def test_returns_required_fields(self):
        d = design_lighting("t", 100, 3.0, "moderate", "park_path")
        s = size_solar_alternative(d)
        for key in ("panel_wattage", "battery_capacity_wh", "autonomy_days",
                    "feasibility_verdict", "worst_month_deficit_kwh",
                    "payback_years_vs_grid"):
            assert key in s, f"missing {key}"

    def test_p3_high_not_viable_standalone(self):
        """P3 / high-activity uses ~60W LEDs and produces a too-large panel."""
        d = design_lighting("p3-test", 200, 3.0, "high", "park_path")
        s = size_solar_alternative(d)
        assert s["feasibility_verdict"] in ("hybrid_only", "not_viable")
        # Panel wattage per light must exceed the standalone cap
        assert s["panel_wattage"] > 250

    def test_low_led_passes_standalone_threshold(self):
        """A design whose LED is well below the 20W standalone cap should
        pass the panel/LED standalone test if other inputs allow."""
        d = design_lighting("p10-mini", 60, 3.0, "low", "park_path")
        # Force a 15W LED to hit the KB-cited standalone band
        d.led_wattage = 15
        d.led_lumens = 2500
        d.total_system_wattage = d.num_lights * d.led_wattage
        s = size_solar_alternative(d)
        assert s["feasibility_verdict"] == "viable_standalone"
        # Worst-month deficit should be small / zero when generation matches consumption
        assert s["worst_month_deficit_kwh"] >= 0

    def test_autonomy_days_affects_battery(self):
        d = design_lighting("p9-test", 100, 3.0, "moderate", "park_path")
        s4 = size_solar_alternative(d, autonomy_days=4)
        s7 = size_solar_alternative(d, autonomy_days=7)
        assert s7["battery_capacity_wh"] > s4["battery_capacity_wh"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
