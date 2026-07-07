from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.config import settings


def business_tz() -> ZoneInfo:
    return ZoneInfo(settings.business_timezone)


def business_today() -> date:
    return datetime.now(business_tz()).date()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_business_date_not_future(v: date | None) -> date | None:
    if v is None:
        return None
    if v > business_today():
        raise ValueError("Date cannot be in the future")
    return v


def business_datetime_for_date(entry_date: date) -> datetime:
    """Map a business calendar date to a UTC timestamp for storage."""
    if entry_date >= business_today():
        return utc_now()
    local_dt = datetime.combine(entry_date, time(12, 0), tzinfo=business_tz())
    return local_dt.astimezone(timezone.utc)


def resolve_business_entry(optional_date: date | None) -> tuple[date, datetime]:
    """Resolve optional user date to (business_date, utc_timestamp)."""
    entry_date = optional_date if optional_date is not None else business_today()
    validate_business_date_not_future(entry_date)
    return entry_date, business_datetime_for_date(entry_date)
