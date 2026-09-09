"""Time, timezone, session and market-calendar utilities.

Everything internal is timezone-aware UTC. Conversion to the user's timezone
happens at the presentation boundary only.

Session definitions (configurable, see SESSION_DEFINITIONS) are expressed in the
local time of the session's home exchange so daylight-saving transitions are
handled by the zoneinfo database instead of hand-coded offsets.

Spot gold (XAU/USD) trades continuously from Sunday 18:00 New York time to
Friday 17:00 New York time, with a daily maintenance break 17:00-18:00 NY.
Holidays and early closes come from the TradingCalendarProvider, not from here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = UTC
NY = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")
TOKYO = ZoneInfo("Asia/Tokyo")


class Session(str, Enum):
    ASIA = "ASIA"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"


class MarketState(str, Enum):
    OPEN = "OPEN"
    MAINTENANCE = "MAINTENANCE"
    WEEKEND = "WEEKEND"
    HOLIDAY = "HOLIDAY"
    EARLY_CLOSE = "EARLY_CLOSE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SessionDefinition:
    session: Session
    tz: ZoneInfo
    start: time
    end: time


SESSION_DEFINITIONS: tuple[SessionDefinition, ...] = (
    SessionDefinition(Session.ASIA, TOKYO, time(9, 0), time(18, 0)),
    SessionDefinition(Session.LONDON, LONDON, time(8, 0), time(16, 30)),
    SessionDefinition(Session.NEW_YORK, NY, time(8, 0), time(17, 0)),
)


def ensure_utc(dt: datetime) -> datetime:
    """Reject naive datetimes. Convert aware datetimes to UTC."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("naive datetime is not allowed; timestamps must be timezone-aware")
    return dt.astimezone(UTC)


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def resolve_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"unknown timezone: {name}") from exc


def to_user_tz(dt: datetime, tz_name: str) -> datetime:
    return ensure_utc(dt).astimezone(resolve_tz(tz_name))


def active_sessions(ts: datetime) -> list[Session]:
    ts = ensure_utc(ts)
    out: list[Session] = []
    for d in SESSION_DEFINITIONS:
        local = ts.astimezone(d.tz)
        if d.start <= local.time() < d.end and local.weekday() < 5:
            out.append(d.session)
    return out


def session_label(ts: datetime) -> str:
    s = active_sessions(ts)
    if not s:
        return "OFF_HOURS"
    if Session.LONDON in s and Session.NEW_YORK in s:
        return "LONDON_NY_OVERLAP"
    return "+".join(x.value for x in s)


def session_bounds_utc(session: Session, on_day: date) -> tuple[datetime, datetime]:
    """UTC start/end of the given session on the given *local* calendar day."""
    d = next(x for x in SESSION_DEFINITIONS if x.session == session)
    start = datetime.combine(on_day, d.start, tzinfo=d.tz).astimezone(UTC)
    end = datetime.combine(on_day, d.end, tzinfo=d.tz).astimezone(UTC)
    return start, end


def market_state(ts: datetime, holiday_dates: set[date] | None = None, early_close_ny: dict[date, time] | None = None) -> MarketState:
    """Spot gold market state at ``ts``.

    ``holiday_dates`` and ``early_close_ny`` are NY-local calendar dates supplied by
    the trading-calendar provider. If the provider cannot be verified the caller
    must pass None for both and treat the result as unverified (see gates).
    """
    ts = ensure_utc(ts)
    local = ts.astimezone(NY)
    wd = local.weekday()  # Mon=0 .. Sun=6
    t = local.time()
    if wd == 5:
        return MarketState.WEEKEND
    if wd == 6 and t < time(18, 0):
        return MarketState.WEEKEND
    if wd == 4 and t >= time(17, 0):
        return MarketState.WEEKEND
    if holiday_dates and local.date() in holiday_dates:
        return MarketState.HOLIDAY
    if early_close_ny and local.date() in early_close_ny and t >= early_close_ny[local.date()]:
        return MarketState.EARLY_CLOSE
    if wd < 4 and time(17, 0) <= t < time(18, 0):
        return MarketState.MAINTENANCE
    return MarketState.OPEN


def is_dst_transition_day(d: date, tz: ZoneInfo) -> bool:
    a = datetime.combine(d, time(0, 0), tzinfo=tz).utcoffset()
    b = datetime.combine(d, time(23, 59), tzinfo=tz).utcoffset()
    return a != b


def week_start_utc(ts: datetime) -> datetime:
    """Monday 00:00 UTC of the ISO week containing ts."""
    ts = ensure_utc(ts)
    monday = (ts - timedelta(days=ts.weekday())).date()
    return datetime.combine(monday, time(0, 0), tzinfo=UTC)


def day_start_utc(ts: datetime) -> datetime:
    ts = ensure_utc(ts)
    return datetime.combine(ts.date(), time(0, 0), tzinfo=UTC)


def parse_local_time(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


def friday_cutoff_utc(ts: datetime, tz_name: str, cutoff_local: str) -> datetime:
    """The user's Friday cutoff for the week containing ts, expressed in UTC."""
    tz = resolve_tz(tz_name)
    local = ensure_utc(ts).astimezone(tz)
    friday = (local - timedelta(days=local.weekday())).date() + timedelta(days=4)
    return datetime.combine(friday, parse_local_time(cutoff_local), tzinfo=tz).astimezone(UTC)


def past_friday_cutoff(ts: datetime, tz_name: str, cutoff_local: str) -> bool:
    cutoff = friday_cutoff_utc(ts, tz_name, cutoff_local)
    ts = ensure_utc(ts)
    return cutoff <= ts < cutoff + timedelta(days=3)
