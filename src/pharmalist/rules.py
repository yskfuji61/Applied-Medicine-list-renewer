from __future__ import annotations


def determine_adoption_status(source_schema: str, adoption_flag: str | None) -> str:
    if source_schema == "old_worksheet":
        return "legacy"

    if adoption_flag is None:
        return "pending"

    normalized = adoption_flag.strip()
    if normalized.startswith("1"):
        return "adopted"
    if normalized.startswith("2"):
        return "discontinued"
    if normalized.startswith("3"):
        return "excluded"
    return "pending"


def should_include_in_adoption_views(adoption_status: str | None) -> bool:
    return adoption_status in {"adopted", "legacy"}