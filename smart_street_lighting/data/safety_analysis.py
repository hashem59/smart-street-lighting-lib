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



# NOTE: The risk-scoring formula (`calculate_safety_score`) and P-category
# adjustment (`adjust_p_category`) were moved out of the plugin in v0.2.0.
# They now live transparently in the submission notebook
# (UC01_Smart_Street_Lighting_RAG_submission.ipynb) so the marker can read
# the formula. Plugin keeps the I/O (crime CSV loader + LGA lookups) only.
