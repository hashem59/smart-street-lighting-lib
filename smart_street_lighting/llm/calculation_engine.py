"""
Lighting Calculation Engine.

Deterministic calculations for street lighting design based on
AS/NZS 1158 standards. This is the core computation layer — the LLM
explains and justifies, but the numbers come from here.
"""

import math
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# AS/NZS 1158 P-Category Standards Lookup
# ============================================================

P_CATEGORIES = {
    "P1": {
        "name": "Major pedestrian activity",
        "avg_lux": 14.0,
        "min_lux": 7.0,
        "uniformity": 0.50,
    },
    "P2": {
        "name": "High-activity pedestrian",
        "avg_lux": 10.0,
        "min_lux": 5.0,
        "uniformity": 0.50,
    },
    "P3": {
        "name": "Moderate pedestrian",
        "avg_lux": 7.0,
        "min_lux": 3.5,
        "uniformity": 0.50,
    },
    "P4": {
        "name": "Moderate-low pedestrian",
        "avg_lux": 5.0,
        "min_lux": 2.5,
        "uniformity": 0.50,
    },
    "P5": {
        "name": "Low pedestrian",
        "avg_lux": 3.5,
        "min_lux": 1.75,
        "uniformity": 0.50,
    },
    "P6": {
        "name": "Low-activity pedestrian",
        "avg_lux": 3.5,
        "min_lux": 0.75,
        "uniformity": 0.21,
    },
    "P7": {
        "name": "Minor pedestrian",
        "avg_lux": 1.5,
        "min_lux": 0.75,
        "uniformity": 0.50,
    },
    "P8": {
        "name": "Minor pedestrian (low risk)",
        "avg_lux": 1.5,
        "min_lux": 0.38,
        "uniformity": 0.25,
    },
    "P9": {
        "name": "Park paths (moderate use)",
        "avg_lux": 2.0,
        "min_lux": 1.0,
        "uniformity": 0.50,
    },
    "P10": {
        "name": "Park paths (low use)",
        "avg_lux": 1.0,
        "min_lux": 0.50,
        "uniformity": 0.50,
    },
    "P11": {
        "name": "Outdoor car parks (commercial)",
        "avg_lux": 7.0,
        "min_lux": 1.75,
        "uniformity": 0.25,
    },
    "P12": {
        "name": "Outdoor car parks (residential)",
        "avg_lux": 3.5,
        "min_lux": 0.88,
        "uniformity": 0.25,
    },
}

# ============================================================
# LED Technology Specs (typical values for Melbourne)
# ============================================================

LED_SPECS = {
    "low": {
        "wattage": 30,
        "lumens": 4500,
        "description": "30W LED (park path bollard/low-mount)",
    },
    "medium": {
        "wattage": 60,
        "lumens": 9000,
        "description": "60W LED (pedestrian area standard)",
    },
    "high": {
        "wattage": 100,
        "lumens": 15000,
        "description": "100W LED (major pathway/road)",
    },
    "very_high": {
        "wattage": 150,
        "lumens": 22500,
        "description": "150W LED (intersection/high-activity)",
    },
}

# ============================================================
# Melbourne Energy Constants
# ============================================================

OPERATING_HOURS_PER_YEAR = 4200  # dusk to dawn average for Melbourne
ELECTRICITY_RATE_PER_KWH = 0.20  # AUD, mid-range Victorian rate
CARBON_FACTOR_VIC_SCOPE2_3 = 1.08  # kg CO2-e per kWh (Scope 2: 0.96 + Scope 3: 0.12)
RECOMMENDED_CCT = 3000  # Kelvin (warm white, Melbourne ecological guideline)
LED_MAINTENANCE_FACTOR = 0.87  # typical for LED luminaires
LED_LIFESPAN_YEARS = 20
LED_CRI = 70
HPS_LIFESPAN_YEARS = 4        # industry mid-range, 3-5 yrs (S4-03)
HPS_REPLACEMENT_COST_AUD = 350  # mid-range bulb + ballast + labour per light

# Pedestrian-volume thresholds for activity-level selection (S4-01 / item 10).
# AS/NZS 1158 itself describes P-category activity qualitatively ("major",
# "high", "moderate", "low" pedestrian). The numerical bands below are the
# project's engineering convention, grounded in:
#   - Austroads Guide to Road Design Part 6B (free, austroads.com.au):
#     "moderate" footway flow ~300-1000 ped/hr; "high" >= 1000 ped/hr.
#   - City of Melbourne Public Lighting Strategy (free, web): same hierarchy
#     break at ~1000 ped/hr for high-activity precincts.
#   - data/knowledge_base/lighting_design_methodology.md Step 1.
# The 50 ped/hr lower boundary is a project engineering choice (noise floor
# to prevent single late-night joggers from triggering a P9 upgrade); it is
# not a standards-cited number and is documented as such.
PED_THRESHOLD_LOW = 50         # below this -> "low" activity (project convention)
PED_THRESHOLD_MODERATE = 300   # Austroads Part 6B "moderate" footway lower bound
PED_THRESHOLD_HIGH = 1000      # Austroads Part 6B "high" footway lower bound

# Solar-PV alternative (S5-08 / item 03)
# All constants from data/knowledge_base/solar_lighting_systems.md (BOM 086071).
SOLAR_PEAK_SUN_HOURS_WORST_MONTH = 1.61   # June, Melbourne Olympic Park
SOLAR_SYSTEM_LOSS_FACTOR = 1.20           # 20% controller + wiring + battery losses
SOLAR_PANEL_EFFICIENCY = 0.85             # standard derate
SOLAR_BATTERY_DOD = 0.80                  # LiFePO4 depth of discharge
SOLAR_BATTERY_VOLTAGE = 12                # V, standard
SOLAR_NIGHT_HOURS_WINTER = 14             # Melbourne winter night length
SOLAR_AUTONOMY_DAYS_DEFAULT = 4           # cloudy-period buffer (KB rec)
SOLAR_STANDALONE_MAX_LED_W = 20           # KB viability table cap
SOLAR_STANDALONE_MAX_PANEL_W = 250        # practical pole-mounted limit
SOLAR_HYBRID_MAX_LED_W = 60
SOLAR_HYBRID_MAX_PANEL_W = 400
SOLAR_HYBRID_ADD_ON_COST_AUD = 2000       # KB benchmark mid-range ($1500-3000)
SOLAR_STANDALONE_COST_PER_LIGHT_AUD = 4000  # KB benchmark mid-range ($3000-5000)
SOLAR_DAYS_PER_MONTH = 30


@dataclass
class LightingDesign:
    """Complete lighting design output from the calculation engine."""

    # Input parameters
    location_name: str
    pathway_length_m: float
    pathway_width_m: float = 3.0
    activity_level: str = "moderate"  # low, moderate, high, very_high

    # Category selection
    p_category: str = ""
    category_name: str = ""
    required_avg_lux: float = 0.0
    required_min_lux: float = 0.0
    required_uniformity: float = 0.0

    # Design specs
    pole_height_m: float = 0.0
    spacing_m: float = 0.0
    num_lights: int = 0
    led_spec: str = ""
    led_wattage: int = 0
    led_lumens: int = 0
    colour_temperature_k: int = RECOMMENDED_CCT

    # Energy & cost estimates
    total_system_wattage: float = 0.0
    annual_energy_kwh: float = 0.0
    annual_energy_cost_aud: float = 0.0
    annual_co2_kg: float = 0.0
    capital_cost_per_light_aud: float = 0.0
    total_capital_cost_aud: float = 0.0
    annual_maintenance_cost_aud: float = 0.0

    # Lifecycle (S4-03 / item 02)
    led_lifespan_years: int = LED_LIFESPAN_YEARS
    hps_lifespan_years: int = HPS_LIFESPAN_YEARS
    maintenance_factor: float = LED_MAINTENANCE_FACTOR
    maintained_avg_lux_target: float = 0.0
    lifetime_energy_kwh: float = 0.0
    lifetime_energy_cost_aud: float = 0.0
    lifetime_co2_kg: float = 0.0
    lifetime_maintenance_cost_aud: float = 0.0
    hps_lifetime_energy_kwh: float = 0.0
    hps_lifetime_energy_cost_aud: float = 0.0
    hps_lifetime_replacements: int = 0
    hps_lifetime_replacement_cost_aud: float = 0.0
    lifecycle_savings_aud: float = 0.0

    # Comparison vs HPS baseline
    hps_equivalent_wattage: int = 0
    hps_annual_energy_kwh: float = 0.0
    hps_annual_cost_aud: float = 0.0
    energy_saving_percent: float = 0.0
    co2_saving_kg: float = 0.0
    payback_years: float = 0.0

    # Enhanced: geometry-aware placement, budget, safety
    light_positions: list = field(default_factory=list)
    budget_analysis: dict = field(default_factory=dict)
    safety_adjustment_applied: int = 0
    pathway_geometry: dict = field(default_factory=dict)

    # Data-quality fallbacks surfaced upstream (S5-02 / item 11): a list of
    # {field, fallback_reason} dicts describing where the design used a
    # default instead of real data.
    data_quality: list = field(default_factory=list)

    # AS/NZS 1158 photometric verification (populated by verify_design())
    verification: dict = field(default_factory=dict)

    def verify(self, sample_step_m: float = 0.5,
               maintenance_factor: float | None = None) -> dict:
        """Run AS/NZS 1158 photometric back-check on this design.

        Stores the result on `self.verification` and returns it.
        See `verify_design()` for model details and citations.
        """
        self.verification = verify_design(
            self,
            sample_step_m=sample_step_m,
            maintenance_factor=maintenance_factor,
        )
        return self.verification

    def lifecycle_summary(
        self,
        led_lifespan_years: Optional[int] = None,
        hps_lifespan_years: Optional[int] = None,
        hps_replacement_cost_per_light_aud: float = HPS_REPLACEMENT_COST_AUD,
    ) -> dict:
        """
        Integrate LED energy + maintenance against an HPS baseline over the
        LED lifespan, accounting for HPS lumen-decay replacements every
        ``hps_lifespan_years`` (default 4).

        Also sets the *maintained-lumen design target*:
        ``maintained_avg_lux_target = required_avg_lux / maintenance_factor``.
        Designers should specify a fixture whose *initial* lumen output
        delivers this target so that, after the maintenance factor depreciates
        it, the maintained illuminance still meets the P-category requirement.

        Source: maintenance factor and lumen depreciation as the regulatory
        bar for AS/NZS 1158 — VicRoads supplement; HPS service life 3-5 yrs
        per IPWEA Practice Note on Public Lighting.

        Side-effect: stores all lifetime_* fields on self.
        Returns a dict of the summary for the LLM context layer.
        """
        led_life = led_lifespan_years if led_lifespan_years is not None else self.led_lifespan_years
        hps_life = hps_lifespan_years if hps_lifespan_years is not None else self.hps_lifespan_years
        mf = self.maintenance_factor or LED_MAINTENANCE_FACTOR

        self.lifetime_energy_kwh = self.annual_energy_kwh * led_life
        self.lifetime_energy_cost_aud = self.annual_energy_cost_aud * led_life
        self.lifetime_co2_kg = self.annual_co2_kg * led_life
        self.lifetime_maintenance_cost_aud = self.annual_maintenance_cost_aud * led_life

        self.hps_lifetime_energy_kwh = self.hps_annual_energy_kwh * led_life
        self.hps_lifetime_energy_cost_aud = self.hps_annual_cost_aud * led_life
        self.hps_lifetime_replacements = max(0, led_life // hps_life) if hps_life > 0 else 0
        self.hps_lifetime_replacement_cost_aud = (
            self.num_lights
            * self.hps_lifetime_replacements
            * hps_replacement_cost_per_light_aud
        )

        led_lifetime_total = (
            self.lifetime_energy_cost_aud + self.lifetime_maintenance_cost_aud
        )
        hps_lifetime_total = (
            self.hps_lifetime_energy_cost_aud
            + self.hps_lifetime_replacement_cost_aud
            + self.num_lights * 60 * led_life
        )
        self.lifecycle_savings_aud = hps_lifetime_total - led_lifetime_total

        if self.required_avg_lux > 0 and mf > 0:
            self.maintained_avg_lux_target = round(self.required_avg_lux / mf, 3)

        return {
            "led_lifespan_years": led_life,
            "hps_lifespan_years": hps_life,
            "maintenance_factor": mf,
            "maintained_avg_lux_target": self.maintained_avg_lux_target,
            "led_lifetime": {
                "energy_kwh": round(self.lifetime_energy_kwh, 1),
                "energy_cost_aud": round(self.lifetime_energy_cost_aud, 0),
                "co2_kg": round(self.lifetime_co2_kg, 0),
                "maintenance_cost_aud": round(self.lifetime_maintenance_cost_aud, 0),
                "total_cost_aud": round(led_lifetime_total, 0),
            },
            "hps_lifetime": {
                "energy_kwh": round(self.hps_lifetime_energy_kwh, 1),
                "energy_cost_aud": round(self.hps_lifetime_energy_cost_aud, 0),
                "replacements": self.hps_lifetime_replacements,
                "replacement_cost_aud": round(self.hps_lifetime_replacement_cost_aud, 0),
                "total_cost_aud": round(hps_lifetime_total, 0),
            },
            "lifecycle_savings_aud": round(self.lifecycle_savings_aud, 0),
        }

    def summary_dict(self) -> dict:
        """Return key outputs as a dictionary for LLM context."""
        d = {
            "location": self.location_name,
            "pathway_length_m": self.pathway_length_m,
            "p_category": self.p_category,
            "category_name": self.category_name,
            "required_avg_lux": self.required_avg_lux,
            "num_lights": self.num_lights,
            "spacing_m": self.spacing_m,
            "pole_height_m": self.pole_height_m,
            "led_wattage": self.led_wattage,
            "colour_temperature": f"{self.colour_temperature_k}K",
            "annual_energy_cost_aud": round(self.annual_energy_cost_aud, 2),
            "annual_energy_kwh": round(self.annual_energy_kwh, 1),
            "annual_co2_kg": round(self.annual_co2_kg, 1),
            "total_capital_cost_aud": round(self.total_capital_cost_aud, 2),
            "energy_saving_vs_hps_percent": round(self.energy_saving_percent, 1),
            "co2_saving_vs_hps_kg": round(self.co2_saving_kg, 1),
            "payback_years": round(self.payback_years, 1),
        }
        if self.light_positions:
            d["light_positions"] = self.light_positions
        if self.budget_analysis:
            d["budget_analysis"] = self.budget_analysis
        if self.safety_adjustment_applied:
            d["safety_adjustment_applied"] = self.safety_adjustment_applied
        return d


def select_p_category(activity_level: str, location_type: str = "park_path") -> str:
    """
    Select the appropriate AS/NZS 1158 P-category based on activity level
    and location type.

    AS/NZS 1158 itself describes P-category activity *qualitatively*. The
    "low / moderate / high / very_high" levels map to numerical ped/hr
    bands defined by ``PED_THRESHOLD_LOW``, ``PED_THRESHOLD_MODERATE`` and
    ``PED_THRESHOLD_HIGH``. Those bands are an engineering convention
    grounded in Austroads Guide to Road Design Part 6B (free) and City of
    Melbourne Public Lighting Strategy (free); see the constants for
    citations. The 50-ped/hr lower bound is a project choice, not a
    standards citation.

    The park_path branch skips P4-P8 because those P-categories were
    drafted for car-park and minor-residential contexts; for park paths
    the standard's intent is a step-change in pedestrian density.

    Args:
        activity_level: "low", "moderate", "high", "very_high"
        location_type: "park_path", "shared_path", "public_space", "residential"

    Returns:
        P-category string (e.g., "P3")
    """
    if location_type == "park_path":
        mapping = {"low": "P10", "moderate": "P9", "high": "P3", "very_high": "P2"}
    elif location_type == "shared_path":
        mapping = {"low": "P5", "moderate": "P3", "high": "P2", "very_high": "P1"}
    elif location_type == "public_space":
        mapping = {"low": "P5", "moderate": "P3", "high": "P2", "very_high": "P1"}
    elif location_type == "residential":
        mapping = {"low": "P8", "moderate": "P6", "high": "P5", "very_high": "P4"}
    else:
        mapping = {"low": "P10", "moderate": "P9", "high": "P3", "very_high": "P2"}

    return mapping.get(activity_level, "P9")


def select_led_spec(p_category: str) -> str:
    """Select appropriate LED spec based on the lighting category."""
    high_cats = {"P1", "P2", "P11"}
    medium_cats = {"P3", "P4", "P5"}
    if p_category in high_cats:
        return "high"
    elif p_category in medium_cats:
        return "medium"
    else:
        return "low"


def calculate_spacing(pole_height: float, p_category: str) -> float:
    """
    Calculate recommended spacing based on pole height and category.
    Rule: spacing = multiplier × pole_height (AS/NZS 1158 guidance: 3-5x).
    """
    # Higher categories need closer spacing for uniformity
    multipliers = {
        "P1": 3.0,
        "P2": 3.5,
        "P3": 3.5,
        "P4": 4.0,
        "P5": 4.0,
        "P6": 4.5,
        "P7": 5.0,
        "P8": 5.0,
        "P9": 4.0,
        "P10": 5.0,
        "P11": 4.0,
        "P12": 4.5,
    }
    mult = multipliers.get(p_category, 4.0)
    return round(pole_height * mult, 1)


def select_pole_height(p_category: str, pathway_width: float) -> float:
    """Select pole height based on category and pathway width."""
    if p_category in {"P1", "P2"}:
        return 6.0 if pathway_width >= 3.0 else 5.0
    elif p_category in {"P3", "P4", "P5"}:
        return 5.0 if pathway_width >= 3.0 else 4.0
    else:
        return 4.0 if pathway_width >= 2.0 else 3.5


def design_lighting(
    location_name: str,
    pathway_length_m: float,
    pathway_width_m: float = 3.0,
    activity_level: str = "moderate",
    location_type: str = "park_path",
    avg_pedestrian_count: Optional[float] = None,
    safety_adjustment: int = 0,
    pathway_geometry: Optional[dict] = None,
    intersections: Optional[list] = None,
    entry_points: Optional[list] = None,
    budget_cap: Optional[float] = None,
) -> LightingDesign:
    """
    Complete lighting design calculation for a pathway.

    This is the main entry point for the calculation engine.
    Given physical parameters and activity level, it produces a full
    design with light count, spacing, energy cost, and HPS comparison.

    Args:
        location_name: Name of the location.
        pathway_length_m: Length in metres.
        pathway_width_m: Width in metres.
        activity_level: "low", "moderate", "high", "very_high"
        location_type: "park_path", "shared_path", "public_space", "residential"
        avg_pedestrian_count: Average hourly pedestrian count (if known from data).
        safety_adjustment: P-category adjustment from safety analysis (negative = upgrade).
        pathway_geometry: GeoJSON LineString dict for geometry-aware placement.
        intersections: List of intersection dicts from OSM analysis.
        entry_points: List of entry point dicts from OSM analysis.
        budget_cap: Optional annual budget cap in AUD.

    Returns:
        LightingDesign with all calculations populated.
    """
    # If we have real pedestrian data, override activity level
    if avg_pedestrian_count is not None:
        # Thresholds documented in module constants (S4-01 / item 10).
        if avg_pedestrian_count < PED_THRESHOLD_LOW:
            activity_level = "low"
        elif avg_pedestrian_count < PED_THRESHOLD_MODERATE:
            activity_level = "moderate"
        elif avg_pedestrian_count < PED_THRESHOLD_HIGH:
            activity_level = "high"
        else:
            activity_level = "very_high"

    design = LightingDesign(
        location_name=location_name,
        pathway_length_m=pathway_length_m,
        pathway_width_m=pathway_width_m,
        activity_level=activity_level,
    )

    # 1. Select P-category (with optional safety adjustment)
    design.p_category = select_p_category(activity_level, location_type)
    if safety_adjustment != 0:
        p_num = int(design.p_category.replace("P", ""))
        adjusted = max(1, min(12, p_num + safety_adjustment))
        design.p_category = f"P{adjusted}"
    cat = P_CATEGORIES[design.p_category]
    design.category_name = cat["name"]
    design.required_avg_lux = cat["avg_lux"]
    design.required_min_lux = cat["min_lux"]
    design.required_uniformity = cat["uniformity"]

    # 2. Select pole height and spacing
    design.pole_height_m = select_pole_height(design.p_category, pathway_width_m)
    design.spacing_m = calculate_spacing(design.pole_height_m, design.p_category)

    # 3. Calculate number of lights (fence-post: lights at 0, spacing, 2*spacing, ..., end)
    design.num_lights = max(2, math.floor(pathway_length_m / design.spacing_m) + 1)

    # 4. Select LED technology
    design.led_spec = select_led_spec(design.p_category)
    spec = LED_SPECS[design.led_spec]
    design.led_wattage = spec["wattage"]
    design.led_lumens = spec["lumens"]

    # 5. Energy calculations (LED)
    design.total_system_wattage = design.num_lights * design.led_wattage
    design.annual_energy_kwh = (
        design.total_system_wattage * OPERATING_HOURS_PER_YEAR
    ) / 1000
    design.annual_energy_cost_aud = design.annual_energy_kwh * ELECTRICITY_RATE_PER_KWH
    design.annual_co2_kg = design.annual_energy_kwh * CARBON_FACTOR_VIC_SCOPE2_3

    # 6. Capital cost estimate
    # Capital cost includes luminaire + pole + installation + wiring
    # (luminaire-only costs are 30-40% of total installed cost)
    cost_per_light_installed = {
        "low": 3000,
        "medium": 4500,
        "high": 6000,
        "very_high": 8000,
    }
    design.capital_cost_per_light_aud = cost_per_light_installed[design.led_spec]
    design.total_capital_cost_aud = (
        design.num_lights * design.capital_cost_per_light_aud
    )
    design.annual_maintenance_cost_aud = (
        design.num_lights * 15
    )  # ~$15/light/year for LED

    # 7. HPS baseline comparison
    hps_wattage_map = {"low": 70, "medium": 175, "high": 250, "very_high": 400}
    design.hps_equivalent_wattage = hps_wattage_map[design.led_spec]
    hps_total_w = design.num_lights * design.hps_equivalent_wattage
    design.hps_annual_energy_kwh = (hps_total_w * OPERATING_HOURS_PER_YEAR) / 1000
    design.hps_annual_cost_aud = design.hps_annual_energy_kwh * ELECTRICITY_RATE_PER_KWH

    # 8. Savings
    if design.hps_annual_energy_kwh > 0:
        design.energy_saving_percent = (
            (design.hps_annual_energy_kwh - design.annual_energy_kwh)
            / design.hps_annual_energy_kwh
            * 100
        )
    design.co2_saving_kg = (
        design.hps_annual_energy_kwh - design.annual_energy_kwh
    ) * CARBON_FACTOR_VIC_SCOPE2_3

    # 9. Payback period (retrofit scenario — luminaire replacement only)
    # For retrofits, cost is luminaire + installation only (poles already exist)
    retrofit_cost_per_light = {
        "low": 1000,
        "medium": 1500,
        "high": 2000,
        "very_high": 2800,
    }
    retrofit_total = design.num_lights * retrofit_cost_per_light[design.led_spec]
    annual_saving = (design.hps_annual_cost_aud - design.annual_energy_cost_aud) + (
        design.num_lights * 60
    )  # +$60/light/yr HPS maintenance saving (industry avg)
    if annual_saving > 0:
        design.payback_years = retrofit_total / annual_saving

    # 10. Record safety adjustment
    design.safety_adjustment_applied = safety_adjustment

    # 11. Geometry-aware light placement (if pathway geometry provided)
    if pathway_geometry and pathway_geometry.get("coordinates"):
        try:
            from smart_street_lighting.data.geometry import place_lights_on_polyline

            coords_lonlat = pathway_geometry["coordinates"]
            coords = [(c[1], c[0]) for c in coords_lonlat]  # GeoJSON is [lon, lat]
            design.light_positions = place_lights_on_polyline(
                coords,
                design.spacing_m,
                intersections=intersections,
                entry_points=entry_points,
            )
            design.pathway_geometry = pathway_geometry
            # Update light count to match actual placed lights
            if design.light_positions:
                design.num_lights = len(design.light_positions)
                # Recalculate energy/cost with updated light count
                design.total_system_wattage = design.num_lights * design.led_wattage
                design.annual_energy_kwh = (
                    design.total_system_wattage * OPERATING_HOURS_PER_YEAR
                ) / 1000
                design.annual_energy_cost_aud = (
                    design.annual_energy_kwh * ELECTRICITY_RATE_PER_KWH
                )
                design.annual_co2_kg = (
                    design.annual_energy_kwh * CARBON_FACTOR_VIC_SCOPE2_3
                )
                design.total_capital_cost_aud = (
                    design.num_lights * design.capital_cost_per_light_aud
                )
                design.annual_maintenance_cost_aud = design.num_lights * 15
                hps_total_w = design.num_lights * design.hps_equivalent_wattage
                design.hps_annual_energy_kwh = (
                    hps_total_w * OPERATING_HOURS_PER_YEAR
                ) / 1000
                design.hps_annual_cost_aud = (
                    design.hps_annual_energy_kwh * ELECTRICITY_RATE_PER_KWH
                )
                if design.hps_annual_energy_kwh > 0:
                    design.energy_saving_percent = (
                        (design.hps_annual_energy_kwh - design.annual_energy_kwh)
                        / design.hps_annual_energy_kwh
                        * 100
                    )
                design.co2_saving_kg = (
                    design.hps_annual_energy_kwh - design.annual_energy_kwh
                ) * CARBON_FACTOR_VIC_SCOPE2_3
                retrofit_total = (
                    design.num_lights * retrofit_cost_per_light[design.led_spec]
                )
                annual_saving = (
                    design.hps_annual_cost_aud - design.annual_energy_cost_aud
                ) + (design.num_lights * 60)
                if annual_saving > 0:
                    design.payback_years = retrofit_total / annual_saving
        except Exception as e:
            print(f"Geometry placement failed, using linear calculation: {e}")

    # 12. Budget analysis
    if budget_cap is not None:
        total_annual = (
            design.annual_energy_cost_aud + design.annual_maintenance_cost_aud
        )
        within_budget = total_annual <= budget_cap

        budget_alt = None
        compliance_notes = []
        if not within_budget:
            # Try wider spacing (up to 1.3x) and lower wattage
            alt_spacing = design.spacing_m * 1.3
            alt_num_lights = max(2, math.floor(pathway_length_m / alt_spacing) + 1)
            # Try one LED spec level lower
            spec_order = ["very_high", "high", "medium", "low"]
            current_idx = (
                spec_order.index(design.led_spec)
                if design.led_spec in spec_order
                else -1
            )
            alt_spec_key = (
                spec_order[min(current_idx + 1, len(spec_order) - 1)]
                if current_idx >= 0
                else design.led_spec
            )
            alt_spec = LED_SPECS[alt_spec_key]

            alt_energy = (
                alt_num_lights * alt_spec["wattage"] * OPERATING_HOURS_PER_YEAR
            ) / 1000
            alt_cost = alt_energy * ELECTRICITY_RATE_PER_KWH
            alt_maint = alt_num_lights * 15
            alt_total = alt_cost + alt_maint

            budget_alt = {
                "num_lights": alt_num_lights,
                "spacing_m": round(alt_spacing, 1),
                "led_wattage": alt_spec["wattage"],
                "annual_energy_cost_aud": round(alt_cost, 2),
                "annual_total_cost_aud": round(alt_total, 2),
            }
            compliance_notes.append(
                f"Budget alternative uses {alt_spacing:.1f}m spacing (1.3x standard), "
                f"which may reduce uniformity below AS/NZS 1158 requirements."
            )

        design.budget_analysis = {
            "budget_cap": budget_cap,
            "within_budget": within_budget,
            "full_design_annual_cost": round(total_annual, 2),
            "budget_alternative": budget_alt,
            "compliance_notes": compliance_notes,
        }

    # 13. Lifecycle summary (S4-03 / item 02): integrates MF + lifespan
    try:
        design.lifecycle_summary()
    except Exception:
        # Don't break callers if some sub-call errors; lifecycle is informational.
        pass

    return design



def size_solar_alternative(
    design: "LightingDesign",
    autonomy_days: int = SOLAR_AUTONOMY_DAYS_DEFAULT,
) -> dict:
    """
    Compute a solar-PV alternative for a given LED LightingDesign and
    return its feasibility verdict for Melbourne.

    Method follows the four-step solar-sizing procedure documented in
    ``data/knowledge_base/solar_lighting_systems.md`` (compiled from BOM
    irradiance data and Australian solar deployment reports):

    1. Daily Wh per light = LED_W * winter_night_hours * loss_factor (1.20).
    2. Panel W per light = daily_Wh / peak_sun_hours_worst_month / panel_eta.
       (Melbourne worst month = June, 1.61 peak sun hours from BOM 086071.)
    3. Battery (Ah) per light = daily_Wh * autonomy_days / DoD / V_bat.
       Convert to Wh for the standard-shape return.
    4. Worst-month deficit = (generated - consumed) clamped at zero, scaled
       per month per the system.

    Three-level feasibility verdict
    -------------------------------
    - "viable_standalone": LED <= 20W AND panel <= 250W (KB Key Finding;
      P10 with 15-20W LEDs is the only band that clears both caps).
    - "hybrid_only":       LED <= 60W AND panel <= 400W (grid primary +
      solar offset 30-50% of annual kWh, KB hybrid section).
    - "not_viable":        anything else; grid required, no useful offset.

    Payback (years) is estimated against a grid-only baseline:
        payback = capital_added / annual_solar_savings
    where the standalone case uses the full standalone capital and saves
    the entire annual energy cost, and the hybrid case uses the add-on
    cost and saves the KB-cited 40% of annual energy cost.

    Args:
        design: a populated LightingDesign.
        autonomy_days: cloudy-period buffer (default 4 per KB).

    Returns:
        dict with the seven backlog-required fields plus notes.
    """
    led_w = design.led_wattage
    num_lights = max(1, design.num_lights)

    # Step 1: daily Wh per light
    daily_wh_per_light = led_w * SOLAR_NIGHT_HOURS_WINTER * SOLAR_SYSTEM_LOSS_FACTOR

    # Step 2: panel wattage per light
    panel_w_per_light = (
        daily_wh_per_light
        / SOLAR_PEAK_SUN_HOURS_WORST_MONTH
        / SOLAR_PANEL_EFFICIENCY
    )

    # Step 3: battery capacity per light
    battery_ah_per_light = (
        daily_wh_per_light * autonomy_days
        / SOLAR_BATTERY_DOD
        / SOLAR_BATTERY_VOLTAGE
    )
    battery_wh_per_light = battery_ah_per_light * SOLAR_BATTERY_VOLTAGE

    # Step 4: worst-month deficit at system level (kWh / month)
    monthly_consumption_wh = (
        led_w * SOLAR_NIGHT_HOURS_WINTER * SOLAR_DAYS_PER_MONTH * num_lights
    )
    monthly_generation_wh_per_light = (
        panel_w_per_light
        * SOLAR_PEAK_SUN_HOURS_WORST_MONTH
        * SOLAR_PANEL_EFFICIENCY
        * SOLAR_DAYS_PER_MONTH
    )
    monthly_generation_wh = monthly_generation_wh_per_light * num_lights
    worst_month_deficit_kwh = max(
        0.0, (monthly_consumption_wh - monthly_generation_wh) / 1000.0
    )

    # Verdict
    standalone_ok = (
        led_w <= SOLAR_STANDALONE_MAX_LED_W
        and panel_w_per_light <= SOLAR_STANDALONE_MAX_PANEL_W
    )
    hybrid_ok = (
        led_w <= SOLAR_HYBRID_MAX_LED_W
        and panel_w_per_light <= SOLAR_HYBRID_MAX_PANEL_W
    )
    if standalone_ok:
        verdict = "viable_standalone"
    elif hybrid_ok:
        verdict = "hybrid_only"
    else:
        verdict = "not_viable"

    # Payback estimation (years vs grid)
    if verdict == "viable_standalone":
        capital_added = SOLAR_STANDALONE_COST_PER_LIGHT_AUD * num_lights
        annual_savings = design.annual_energy_cost_aud
    elif verdict == "hybrid_only":
        capital_added = SOLAR_HYBRID_ADD_ON_COST_AUD * num_lights
        # KB hybrid section: 30-50% of grid offset; midrange 40%
        annual_savings = 0.40 * design.annual_energy_cost_aud
    else:
        capital_added = SOLAR_HYBRID_ADD_ON_COST_AUD * num_lights
        annual_savings = 0.0

    if annual_savings > 0:
        payback_years_vs_grid = round(capital_added / annual_savings, 1)
    else:
        payback_years_vs_grid = float("inf")

    notes = []
    if verdict == "viable_standalone":
        notes.append(
            f"Standalone viable: LED {led_w}W and panel "
            f"{panel_w_per_light:.0f}W per light both within the practical caps."
        )
    elif verdict == "hybrid_only":
        notes.append(
            f"Standalone exceeds the practical panel/LED caps "
            f"({led_w}W LED, {panel_w_per_light:.0f}W panel); recommend "
            f"hybrid (grid primary + solar offset ~40% annual kWh per KB)."
        )
    else:
        notes.append(
            f"Not viable: {led_w}W LED above {SOLAR_HYBRID_MAX_LED_W}W "
            f"hybrid cap and {panel_w_per_light:.0f}W panel above "
            f"{SOLAR_HYBRID_MAX_PANEL_W}W. Grid only is the only practical option."
        )
    if worst_month_deficit_kwh > 0:
        notes.append(
            f"Worst-month (June) generation deficit: "
            f"{worst_month_deficit_kwh:.1f} kWh — would require grid backup "
            f"or extra battery capacity to cover."
        )

    return {
        "panel_wattage": round(panel_w_per_light, 0),
        "panel_wattage_total_system": round(panel_w_per_light * num_lights, 0),
        "battery_capacity_wh": round(battery_wh_per_light, 0),
        "battery_capacity_ah": round(battery_ah_per_light, 0),
        "autonomy_days": autonomy_days,
        "feasibility_verdict": verdict,
        "worst_month_deficit_kwh": round(worst_month_deficit_kwh, 1),
        "payback_years_vs_grid": payback_years_vs_grid,
        "capital_added_aud": round(capital_added, 0),
        "annual_savings_aud": round(annual_savings, 0),
        "notes": notes,
    }


def verify_design(
    design: "LightingDesign",
    sample_step_m: float = 0.5,
    maintenance_factor: Optional[float] = None,
) -> dict:
    """
    Photometric back-check: does the designed layout actually deliver
    the AS/NZS 1158 P-category illuminance and uniformity it was sized for?

    Model
    -----
    Conservative cosine-cubed point-source approximation (the lower-bound
    illuminance model used in industry verification workflows when a full
    IES luminaire file is not available):

        E(x) = sum over lights of (I0 * MF * cos^3(theta)) / (h^2 + d^2)

    where:
        I0  = lumens / (4 * pi)   isotropic-equivalent intensity
        MF  = maintenance factor  (defaults to LED_MAINTENANCE_FACTOR = 0.87)
        h   = pole height         (m)
        d   = horizontal distance from the receiver to the luminaire foot (m)
        cos(theta) = h / sqrt(h^2 + d^2)

    Because real luminaires bias their flux downward via reflectors and
    refractive optics, the isotropic model under-reports the achieved
    illuminance. A 'compliant' result here is therefore a strict lower-bound
    pass; a 'non-compliant' result means the design is close enough to the
    limit that a true photometric simulation (DIALux/IES) is required
    before construction sign-off.

    Sources
    -------
    - Formula and verification grid spacing: project KB
      `data/knowledge_base/lighting_design_methodology.md` Step 3
      (paraphrased from AS/NZS 1158 design guides) and IESNA Lighting
      Handbook 10th ed., section 10 (point-source method).
    - Maintenance factor as the regulatory bar: VicRoads supplement
      (`data/downloaded_sources/vicroads_supplement_as1158.pdf`).

    Limitations
    -----------
    - Geometric only: no beam-shape optics, no inter-reflections, no
      vertical or semi-cylindrical illuminance.
    - Assumes evenly spaced fence-post placement along a straight chainage.
      For geometry-aware layouts (`design.light_positions`), the result is
      still a useful 1-D projection but the true minimum may sit off-axis.
    - For pathways shorter than 2 x design.spacing_m, the minimum lies
      between two poles — that is the genuinely darkest point, so a
      'fail' verdict on short paths is informative, not a numerical
      artefact.

    Args:
        design: A populated LightingDesign (must have num_lights, spacing_m,
            pole_height_m, led_lumens, pathway_length_m, required_* values).
        sample_step_m: chainage sampling resolution. 0.5 m balances accuracy
            with run-time; KB Step 3 calls for <= 1.5 m.
        maintenance_factor: override the default LED_MAINTENANCE_FACTOR
            (0.87). Pass 1.0 to verify initial (new-install) illuminance,
            or e.g. 0.7 to model end-of-life worst case.

    Returns:
        A dict with achieved metrics, required thresholds, pass booleans,
        compliance verdict, and per-metric deficits. Chainage and lux
        arrays are returned as lists so the result is JSON-serialisable.
    """
    import numpy as np

    mf = LED_MAINTENANCE_FACTOR if maintenance_factor is None else maintenance_factor
    if design.num_lights <= 0 or design.pathway_length_m <= 0:
        # Degenerate input — return a 'cannot verify' shape
        return {
            "chainage_m": [],
            "lux_at_chainage": [],
            "achieved_avg_lux": 0.0,
            "achieved_min_lux": 0.0,
            "achieved_max_lux": 0.0,
            "achieved_uniformity": 0.0,
            "required_avg_lux": design.required_avg_lux,
            "required_min_lux": design.required_min_lux,
            "required_uniformity": design.required_uniformity,
            "maintenance_factor": mf,
            "avg_pass": False,
            "min_pass": False,
            "uniformity_pass": False,
            "compliant": False,
            "deficits": {
                "avg_lux_deficit": design.required_avg_lux,
                "min_lux_deficit": design.required_min_lux,
                "uniformity_deficit": design.required_uniformity,
            },
            "note": "verify_design called on empty / zero-length design",
        }

    positions = [
        min(i * design.spacing_m, design.pathway_length_m)
        for i in range(design.num_lights)
    ]
    h = design.pole_height_m if design.pole_height_m else 4.0
    I0 = design.led_lumens / (4.0 * math.pi)
    xs = np.arange(0.0, design.pathway_length_m + sample_step_m, sample_step_m)
    lux = np.zeros_like(xs, dtype=float)
    for x_p in positions:
        d = xs - x_p
        slant_sq = d * d + h * h
        cos_theta = h / np.sqrt(slant_sq)
        lux += (I0 * mf * cos_theta ** 3) / slant_sq

    e_avg = float(lux.mean())
    e_min = float(lux.min())
    e_max = float(lux.max())
    uniformity = (e_min / e_avg) if e_avg > 0 else 0.0
    avg_pass = e_avg >= design.required_avg_lux
    min_pass = e_min >= design.required_min_lux
    unif_pass = uniformity >= design.required_uniformity

    return {
        "chainage_m": xs.tolist(),
        "lux_at_chainage": lux.tolist(),
        "achieved_avg_lux": round(e_avg, 3),
        "achieved_min_lux": round(e_min, 3),
        "achieved_max_lux": round(e_max, 3),
        "achieved_uniformity": round(uniformity, 3),
        "required_avg_lux": design.required_avg_lux,
        "required_min_lux": design.required_min_lux,
        "required_uniformity": design.required_uniformity,
        "maintenance_factor": mf,
        "avg_pass": avg_pass,
        "min_pass": min_pass,
        "uniformity_pass": unif_pass,
        "compliant": bool(avg_pass and min_pass and unif_pass),
        "deficits": {
            "avg_lux_deficit": max(0.0, design.required_avg_lux - e_avg),
            "min_lux_deficit": max(0.0, design.required_min_lux - e_min),
            "uniformity_deficit": max(0.0, design.required_uniformity - uniformity),
        },
    }


def format_design_report(design: LightingDesign) -> str:
    """Format a human-readable design report from calculations."""
    return f"""
LIGHTING DESIGN CALCULATION REPORT
{'='*50}
Location: {design.location_name}
Pathway: {design.pathway_length_m}m long x {design.pathway_width_m}m wide
Activity Level: {design.activity_level}

CATEGORY SELECTION
  AS/NZS 1158 Category: {design.p_category} — {design.category_name}
  Required average illuminance: {design.required_avg_lux} lux
  Required minimum illuminance: {design.required_min_lux} lux
  Required uniformity (Emin/Eavg): {design.required_uniformity}

DESIGN SPECIFICATIONS
  Number of lights: {design.num_lights}
  Spacing: {design.spacing_m}m
  Pole height: {design.pole_height_m}m
  Technology: {design.led_wattage}W LED ({design.led_lumens} lumens)
  Colour temperature: {design.colour_temperature_k}K (warm white)
  CRI: {LED_CRI}

ENERGY & COST ESTIMATES (LED)
  Total system wattage: {design.total_system_wattage}W
  Annual energy: {design.annual_energy_kwh:.0f} kWh
  Annual energy cost: ${design.annual_energy_cost_aud:.2f}
  Annual CO2 emissions: {design.annual_co2_kg:.1f} kg CO2-e
  Capital cost (new install): ${design.total_capital_cost_aud:,.0f} ({design.num_lights} x ${design.capital_cost_per_light_aud}, includes pole + wiring)

COMPARISON vs HPS BASELINE
  HPS equivalent: {design.hps_equivalent_wattage}W per light
  HPS annual energy cost: ${design.hps_annual_cost_aud:.2f}
  Energy saving: {design.energy_saving_percent:.1f}%
  CO2 saving: {design.co2_saving_kg:.1f} kg CO2-e/year
  Retrofit payback period: {design.payback_years:.1f} years (luminaire swap only)
""".strip()


if __name__ == "__main__":
    # UC-01 test: Fitzroy Gardens pathway
    design = design_lighting(
        location_name="Fitzroy Gardens Main Pathway",
        pathway_length_m=200,
        pathway_width_m=3.0,
        activity_level="high",
        location_type="park_path",
    )
    print(format_design_report(design))
    print()
    print("Summary dict for LLM:")
    for k, v in design.summary_dict().items():
        print(f"  {k}: {v}")
