"""
BFIU Annexure-1 Risk Score Lookup Tables

This module contains the profession and business activity risk score mappings
as specified in BFIU Circular 29 (2026) - Guidelines on e-KYC for Insurance
Companies and Capital Market Intermediaries.
"""

# Annexure-1 profession risk scores (BFIU Circular 29)
PROFESSION_SCORES: dict[str, int] = {
    "pilot": 5,
    "flight_attendant": 5,
    "trustee": 5,
    "journalist": 4,
    "lawyer": 4,
    "advocate": 4,
    "doctor": 4,
    "physician": 4,
    "it_employee": 4,
    "software_engineer": 4,
    "athlete": 4,
    "media_celebrity": 4,
    "government_service": 3,
    "managerial": 3,
    "private_service": 2,
    "self_employed": 2,
    "student": 2,
    "shares_investor": 2,
    "stock_investor": 2,
    "retiree": 1,
}
PROFESSION_DEFAULT_SCORE = 3

# Annexure-1 business activity risk scores (BFIU Circular 29)
BUSINESS_ACTIVITY_SCORES: dict[str, int] = {
    "jeweler": 5,
    "gold_business": 5,
    "money_changer": 5,
    "mfs_agent": 5,
    "real_estate": 5,
    "real_estate_developer": 5,
    "manpower_export": 5,
    "recruitment": 5,
    "art_dealer": 5,
    "antiquities": 5,
    "rmg": 5,
    "garments": 5,
    "software_business": 5,
    "it_business": 5,
    "shares_trading": 5,
    "stock_trading": 5,
    "construction_materials": 4,
    "small_business": 2,
}
BUSINESS_DEFAULT_SCORE = 3


def lookup_score(value: str | None, table: dict[str, int], default: int) -> tuple[int, str]:
    """
    Case-insensitive token match for risk score lookup.

    Args:
        value: The profession or business activity string to look up
        table: The score mapping dictionary
        default: Default score to return if no match found

    Returns:
        Tuple of (score, matched_key_or_default_label)
    """
    if not value:
        return default, "not_provided"

    # Normalize: lowercase, replace spaces/slashes/dashes with underscores
    normalised = (
        value.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
    )

    # Exact match first
    if normalised in table:
        return table[normalised], normalised

    # Partial match: check if any table key is in the normalised value
    for key, score in table.items():
        if key in normalised:
            return score, key

    # Check if normalised value contains any table key (for cases like "Software Engineer")
    for key, score in table.items():
        if key in normalised:
            return score, key

    return default, "unmatched"