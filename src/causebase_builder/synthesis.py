from __future__ import annotations


def deterministic_fixture_summary(source: dict) -> str:
    """Credential-free fixture synthesiser.

    Production synthesis will be provider-backed and governed by EDITORIAL_POLICY.md.
    This function deliberately creates plain, prosaic copy from structured evidence.
    """
    activities = source.get("activities", [])
    beneficiaries = source.get("beneficiaries", [])
    geography = source.get("geography", [])
    participation = source.get("participation_modes", [])

    activity_text = ", ".join(activities[:-1])
    if len(activities) > 1:
        activity_text += f" and {activities[-1]}"
    elif activities:
        activity_text = activities[0]
    else:
        activity_text = "undertakes charitable activities"

    geo_text = "; ".join(geography) if geography else "Australia"
    beneficiary_text = ", ".join(beneficiaries) if beneficiaries else "its target communities"

    sentence = (
        f"{source['display_name']} {activity_text} in {geo_text}, "
        f"serving {beneficiary_text}."
    )
    if participation:
        sentence += " Public participation includes " + ", ".join(participation) + "."
    return sentence
