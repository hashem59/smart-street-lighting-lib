"""
Safety risk assessment using Victoria crime statistics.
Maps crime data to Local Government Areas (LGAs) and produces
a risk score that adjusts AS/NZS 1158 P-category selection.
"""

import pandas as pd
from pathlib import Path

from smart_street_lighting.core.logging import get_logger

log = get_logger(__name__)

# Crime data cache lives under the caller's working directory, not site-packages.
CRIME_DATA_PATH = Path.cwd() / "data" / "cache" / "crime" / "crime_data.csv"

# Mapping of known Melbourne parks/areas to their LGA
PARK_LGA_MAP = {
    "fitzroy gardens": "Melbourne",
    "carlton gardens": "Melbourne",
    "flagstaff gardens": "Melbourne",
    "treasury gardens": "Melbourne",
    "birrarung marr": "Melbourne",
    "melbourne cbd": "Melbourne",
    "princes park": "Melbourne",
    "royal park": "Melbourne",
    "edinburgh gardens": "Yarra",
    "victoria gardens": "Yarra",
    "st kilda botanical gardens": "Port Phillip",
    "albert park": "Port Phillip",
    "prahran square": "Stonnington",
    "footscray park": "Maribyrnong",
    "coburg lake reserve": "Moreland",
    "all nations park": "Moreland",
    "darebin parklands": "Darebin",
    "kew gardens": "Boroondara",
}

# Offence category weights for composite safety score
OFFENCE_WEIGHTS = {
    "Assault": 0.4,
    "Robbery": 0.3,
    "Property Damage": 0.2,
    "Stalking": 0.1,
}

# Relevant offence categories
RELEVANT_OFFENCES = set(OFFENCE_WEIGHTS.keys())


def load_crime_data() -> pd.DataFrame:
    """
    Load Victoria crime statistics from cached CSV.

    Returns:
        DataFrame with columns: lga_name, offence_category, offence_count, rate_per_100k, year
        Filtered to relevant offence categories.
    """
    if not CRIME_DATA_PATH.exists():
        raise FileNotFoundError(
            f"Crime data not found at {CRIME_DATA_PATH}. "
            "Download from data.vic.gov.au or create a fixture file."
        )

    df = pd.read_csv(CRIME_DATA_PATH)
    df = df[df["offence_category"].isin(RELEVANT_OFFENCES)]
    return df


def get_lga_for_location(location: str) -> str:
    """
    Determine which Melbourne LGA a named location falls in.

    Args:
        location: Park or area name (case-insensitive).

    Returns:
        LGA name string. Defaults to "Melbourne" if not found.

    Note:
        This bare-string contract is preserved for back-compat. Use
        :func:`get_lga_with_fallback_info` to receive the structured
        ``{lga_name, fallback_used, fallback_reason}`` shape (S5-02 / item 11).
    """
    key = location.lower().strip()
    return PARK_LGA_MAP.get(key, "Melbourne")


def get_lga_with_fallback_info(location: str) -> dict:
    """
    Structured LGA lookup that surfaces the unknown-location fallback.

    Returns:
        Dict with ``lga_name`` (str), ``fallback_used`` (bool),
        ``fallback_reason`` (str). When the input location is not in the
        ``PARK_LGA_MAP``, this returns the same default ("Melbourne") as
        :func:`get_lga_for_location` but with ``fallback_used=True`` and
        a human-readable reason. (S5-02 / item 11.)
    """
    key = location.lower().strip()
    if key in PARK_LGA_MAP:
        return {
            "lga_name": PARK_LGA_MAP[key],
            "fallback_used": False,
            "fallback_reason": "",
        }
    return {
        "lga_name": "Melbourne",
        "fallback_used": True,
        "fallback_reason": (
            f"Location {location!r} is not in the project's PARK_LGA_MAP; "
            "defaulting to the City of Melbourne LGA for the safety lookup. "
            "Safety score may be inaccurate for locations outside the CBD."
        ),
    }


def calculate_safety_score(lga_name: str) -> dict:
    """
    Compute a composite safety risk score (0-10) for an LGA.

    Uses weighted offence rates compared to Melbourne-wide median.

    Args:
        lga_name: Local Government Area name.

    Returns:
        Dict with safety_risk_score, risk_category, p_category_adjustment,
        key_offences, and recommendation.
    """
    df = load_crime_data()

    # Get rates for this LGA
    lga_data = df[df["lga_name"] == lga_name]
    if lga_data.empty:
        return {
            "lga_name": lga_name,
            "safety_risk_score": 5.0,
            "risk_category": "moderate",
            "p_category_adjustment": 0,
            "key_offences": {},
            "recommendation": f"No crime data available for {lga_name}. Using default risk assessment.",
            "fallback_used": True,
            "fallback_reason": (
                f"No crime data is cached for LGA {lga_name!r}; the safety "
                "score is a neutral default (5.0 / moderate), not a true "
                "risk assessment. The P-category was not adjusted."
            ),
        }

    # Compute weighted score from per-100k rates
    weighted_sum = 0.0
    key_offences = {}

    # Compute Melbourne-wide median rates for comparison
    median_rates = {}
    for offence in RELEVANT_OFFENCES:
        offence_data = df[df["offence_category"] == offence]
        median_rates[offence] = offence_data["rate_per_100k"].median()

    for _, row in lga_data.iterrows():
        offence = row["offence_category"]
        rate = row["rate_per_100k"]
        weight = OFFENCE_WEIGHTS.get(offence, 0)
        median = median_rates.get(offence, rate)

        # Score component: rate relative to median, scaled to 0-10 range
        ratio = rate / median if median > 0 else 1.0
        component = min(10.0, ratio * 5.0)  # 1.0 ratio → 5.0 (median), 2.0 ratio → 10.0
        weighted_sum += component * weight

        if offence == "Assault":
            key_offences["assault_rate"] = rate
            key_offences["vs_median"] = round(ratio, 2)

    score = round(min(10.0, max(0.0, weighted_sum)), 1)

    # Classify risk and determine P-category adjustment
    if score <= 3.5:
        risk_category = "low"
        p_adjustment = 0
        recommendation = (
            f"{lga_name} has below-average crime rates. "
            "Standard lighting levels per AS/NZS 1158 are appropriate."
        )
    elif score <= 6.5:
        risk_category = "moderate"
        p_adjustment = -1  # Upgrade by one category
        recommendation = (
            f"{lga_name} has moderate crime rates. "
            "Recommend upgrading P-category by one level for enhanced safety. "
            "Consider CPTED principles: improved sightlines and reduced concealment."
        )
    else:
        risk_category = "high"
        p_adjustment = -2  # Upgrade by two categories
        recommendation = (
            f"{lga_name} has above-average crime rates (assault rate "
            f"{key_offences.get('vs_median', 'N/A')}x Melbourne median). "
            "Strongly recommend upgrading P-category by two levels. "
            "Apply CPTED principles: eliminate dark spots, ensure 360-degree visibility "
            "at entry points, and consider blue-white CCT for improved facial recognition."
        )

    return {
        "lga_name": lga_name,
        "safety_risk_score": score,
        "risk_category": risk_category,
        "p_category_adjustment": p_adjustment,
        "key_offences": key_offences,
        "recommendation": recommendation,
        "fallback_used": False,
        "fallback_reason": "",
    }


def adjust_p_category(base_category: str, safety_adjustment: int) -> str:
    """
    Apply safety-based adjustment to a P-category.

    Negative adjustment upgrades (e.g., P5 with -1 → P4).
    Clamped to valid range P1-P12.

    Args:
        base_category: Current P-category string (e.g., "P5").
        safety_adjustment: Integer adjustment (negative = upgrade).

    Returns:
        Adjusted P-category string.
    """
    p_num = int(base_category.replace("P", ""))
    adjusted = p_num + safety_adjustment
    adjusted = max(1, min(12, adjusted))
    return f"P{adjusted}"
