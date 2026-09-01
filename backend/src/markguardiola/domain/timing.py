from datetime import UTC, datetime, timedelta


def kickoff_lower_bound(kickoff_at: datetime, precision: str | None) -> datetime:

    if kickoff_at.tzinfo is None:
        raise ValueError()
    value = kickoff_at.astimezone(UTC)
    if precision == "minute":
        return value
    if precision not in {None, "date", "unknown"}:
        raise ValueError()
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def historical_result_available_at(kickoff_at: datetime, precision: str | None) -> datetime:

    earliest = kickoff_lower_bound(kickoff_at, precision)
    latest = earliest if precision == "minute" else earliest + timedelta(days=1)
    return latest + timedelta(hours=3)


def historical_availability_policy(precision: str | None) -> str:
    return "historical_post_match_3h" if precision == "minute" else "historical_day_end_plus_3h"
