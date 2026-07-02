from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import settings


def business_tz() -> ZoneInfo:
    return ZoneInfo(settings.business_timezone)


def business_today() -> date:
    return datetime.now(business_tz()).date()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
