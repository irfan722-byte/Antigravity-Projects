"""Economic-event (news) state machine.

Phases:
  NONE                      no material USD event in scope
  PRE_EVENT_WINDOW          event within notify window; scenario analysis shown, restricted strategies
  PRE_EVENT_LOCKOUT         within the lockout minutes before the release; no new setups
  RELEASE_LOCKOUT           release time passed, waiting for verified actual (+ minimum lockout)
  POST_RELEASE_COOLDOWN     actual verified, cooldown running; spread/price discovery monitored
  POST_RELEASE_CONFIRMATION confirmation window open for news-aware strategies

The machine never infers the unreleased number and never treats "actual beat
consensus" as a directional signal on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Sequence

from .timeutil import ensure_utc


class Importance(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Verification(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICT = "CONFLICT"
    PENDING = "PENDING"


class NewsPhase(str, Enum):
    NONE = "NONE"
    PRE_EVENT_WINDOW = "PRE_EVENT_WINDOW"
    PRE_EVENT_LOCKOUT = "PRE_EVENT_LOCKOUT"
    RELEASE_LOCKOUT = "RELEASE_LOCKOUT"
    POST_RELEASE_COOLDOWN = "POST_RELEASE_COOLDOWN"
    POST_RELEASE_CONFIRMATION = "POST_RELEASE_CONFIRMATION"


LOCKOUT_PHASES = {NewsPhase.PRE_EVENT_LOCKOUT, NewsPhase.RELEASE_LOCKOUT, NewsPhase.POST_RELEASE_COOLDOWN}


@dataclass
class EconomicEvent:
    event_id: str
    name: str
    country: str
    currency: str
    importance: Importance
    scheduled_ts: datetime
    source_tz: str
    category: str
    provider: str
    ingested_ts: datetime
    actual: float | None = None
    consensus: float | None = None
    prior: float | None = None
    revised_prior: float | None = None
    revision_ts: datetime | None = None
    official_source: str = ""
    published_ts: datetime | None = None
    verification: Verification = Verification.PENDING
    higher_is_usd_positive: bool = True
    unit: str = ""
    surprise_std: float | None = None  # historical std of (actual - consensus); None when history insufficient
    surprise_history_n: int = 0

    @property
    def surprise(self) -> float | None:
        if self.actual is None or self.consensus is None:
            return None
        return self.actual - self.consensus

    @property
    def standardised_surprise(self) -> float | None:
        s = self.surprise
        if s is None or not self.surprise_std or self.surprise_history_n < 12:
            return None
        return s / self.surprise_std

    def to_dict(self, user_tz: str | None = None) -> dict:
        from .timeutil import to_user_tz

        d = {
            "event_id": self.event_id,
            "name": self.name,
            "country": self.country,
            "currency": self.currency,
            "importance": self.importance.value,
            "scheduled_ts": self.scheduled_ts.isoformat(),
            "scheduled_local": to_user_tz(self.scheduled_ts, user_tz).isoformat() if user_tz else None,
            "source_tz": self.source_tz,
            "user_tz": user_tz,
            "category": self.category,
            "provider": self.provider,
            "actual": self.actual,
            "consensus": self.consensus,
            "prior": self.prior,
            "revised_prior": self.revised_prior,
            "revision_ts": self.revision_ts.isoformat() if self.revision_ts else None,
            "official_source": self.official_source,
            "published_ts": self.published_ts.isoformat() if self.published_ts else None,
            "ingested_ts": self.ingested_ts.isoformat(),
            "verification": self.verification.value,
            "surprise": self.surprise,
            "standardised_surprise": None if self.standardised_surprise is None else round(self.standardised_surprise, 2),
            "surprise_history_n": self.surprise_history_n,
            "higher_is_usd_positive": self.higher_is_usd_positive,
            "unit": self.unit,
        }
        return d


@dataclass(frozen=True)
class NewsConfig:
    pre_event_notify_minutes: int = 60
    pre_event_lockout_minutes: int = 30
    release_min_lockout_minutes: int = 5
    post_release_cooldown_minutes: int = 10
    confirmation_window_minutes: int = 120
    max_release_delay_minutes: int = 30
    spread_normal_ratio: float = 1.5
    min_importance: Importance = Importance.HIGH


@dataclass
class NewsState:
    phase: NewsPhase
    event: EconomicEvent | None
    seconds_to_event: float | None
    lockout_until: datetime | None
    scenarios: list[dict]
    reaction: dict | None
    reasons: list[str] = field(default_factory=list)
    upcoming: list[EconomicEvent] = field(default_factory=list)
    version: str = "news-sm-v1"

    @property
    def is_lockout(self) -> bool:
        return self.phase in LOCKOUT_PHASES

    def to_dict(self, user_tz: str | None = None) -> dict:
        return {
            "phase": self.phase.value,
            "is_lockout": self.is_lockout,
            "event": self.event.to_dict(user_tz) if self.event else None,
            "seconds_to_event": self.seconds_to_event,
            "lockout_until": self.lockout_until.isoformat() if self.lockout_until else None,
            "scenarios": self.scenarios,
            "reaction": self.reaction,
            "reasons": self.reasons,
            "upcoming": [e.to_dict(user_tz) for e in self.upcoming[:5]],
            "version": self.version,
        }


_IMPORTANCE_RANK = {Importance.LOW: 0, Importance.MEDIUM: 1, Importance.HIGH: 2}


def _scenarios(ev: EconomicEvent, history: dict | None) -> list[dict]:
    """Stronger / weaker / mixed scenario table. Historical reaction stats come from the provider
    with sample sizes; when absent the table says so instead of inventing numbers."""
    h = history or {}
    n = h.get("sample_size", 0)
    def stat(key: str) -> dict:
        s = h.get(key) or {}
        return {"gold_median_move_30m": s.get("gold_median_move_30m"), "gold_iqr_30m": s.get("gold_iqr_30m"), "reversal_rate_2h": s.get("reversal_rate_2h"), "sample_size": s.get("n", 0)}
    usd_pos = "USD-positive; gold historically pressured" if ev.higher_is_usd_positive else "USD-negative; gold historically supported"
    usd_neg = "USD-negative; gold historically supported" if ev.higher_is_usd_positive else "USD-positive; gold historically pressured"
    return [
        {"scenario": "STRONGER_THAN_CONSENSUS", "interpretation": usd_pos, "history": stat("stronger"), "note": "Not a prediction. Reaction depends on revisions, components and positioning."},
        {"scenario": "WEAKER_THAN_CONSENSUS", "interpretation": usd_neg, "history": stat("weaker"), "note": "Not a prediction."},
        {"scenario": "MIXED_OR_IN_LINE", "interpretation": "Two-sided; revisions and sub-components dominate; frequent whipsaw", "history": stat("inline"), "note": "Not a prediction."},
        {"total_history_sample": n, "history_source": h.get("source", "unavailable")},
    ]


def assess_news_state(
    events: Sequence[EconomicEvent],
    now: datetime,
    cfg: NewsConfig = NewsConfig(),
    spread_now: float | None = None,
    median_spread: float | None = None,
    reaction_inputs: dict | None = None,
    history_by_category: dict | None = None,
) -> NewsState:
    now = ensure_utc(now)
    material = [e for e in events if e.currency == "USD" and _IMPORTANCE_RANK[e.importance] >= _IMPORTANCE_RANK[cfg.min_importance]]
    material.sort(key=lambda e: e.scheduled_ts)
    upcoming = [e for e in material if e.scheduled_ts > now]
    reasons: list[str] = []

    # 1) Most recent past event still inside its post-release life-cycle?
    past = [e for e in material if e.scheduled_ts <= now]
    if past:
        ev = past[-1]
        since = (now - ev.scheduled_ts).total_seconds() / 60.0
        min_lock = ev.scheduled_ts + timedelta(minutes=cfg.release_min_lockout_minutes)
        verified = ev.verification == Verification.VERIFIED and ev.actual is not None
        conflict = ev.verification == Verification.CONFLICT
        hist = (history_by_category or {}).get(ev.category)
        if since <= cfg.confirmation_window_minutes + cfg.post_release_cooldown_minutes:
            if conflict:
                reasons.append(f"{ev.name}: providers disagree on the actual value; unresolved")
                return NewsState(NewsPhase.RELEASE_LOCKOUT, ev, 0.0, None, _scenarios(ev, hist), None, reasons, upcoming)
            if not verified or now < min_lock:
                if since > cfg.max_release_delay_minutes and not verified:
                    reasons.append(f"{ev.name}: release delayed > {cfg.max_release_delay_minutes} min without verified actual")
                else:
                    reasons.append(f"{ev.name}: waiting for verified actual ({since:.0f} min since schedule)")
                return NewsState(NewsPhase.RELEASE_LOCKOUT, ev, 0.0, min_lock, _scenarios(ev, hist), None, reasons, upcoming)
            published = ev.published_ts or ev.scheduled_ts
            cool_until = max(published, ev.scheduled_ts) + timedelta(minutes=cfg.post_release_cooldown_minutes)
            spread_ok = spread_now is None or median_spread is None or spread_now <= cfg.spread_normal_ratio * median_spread
            reaction = _build_reaction(ev, reaction_inputs or {})
            if now < cool_until or not spread_ok:
                reasons.append(f"{ev.name}: cooldown until {cool_until.isoformat()}" if now < cool_until else f"{ev.name}: spread {spread_now:.2f} still > {cfg.spread_normal_ratio}x median")
                return NewsState(NewsPhase.POST_RELEASE_COOLDOWN, ev, 0.0, cool_until, _scenarios(ev, hist), reaction, reasons, upcoming)
            reasons.append(f"{ev.name}: verified; confirmation window open")
            return NewsState(NewsPhase.POST_RELEASE_CONFIRMATION, ev, 0.0, None, _scenarios(ev, hist), reaction, reasons, upcoming)

    # 2) Next upcoming event
    if upcoming:
        ev = upcoming[0]
        secs = (ev.scheduled_ts - now).total_seconds()
        hist = (history_by_category or {}).get(ev.category)
        if secs <= cfg.pre_event_lockout_minutes * 60:
            reasons.append(f"{ev.name} in {secs / 60:.0f} min: pre-event lockout")
            return NewsState(NewsPhase.PRE_EVENT_LOCKOUT, ev, secs, ev.scheduled_ts, _scenarios(ev, hist), None, reasons, upcoming)
        if secs <= cfg.pre_event_notify_minutes * 60:
            reasons.append(f"{ev.name} in {secs / 60:.0f} min: pre-event window")
            return NewsState(NewsPhase.PRE_EVENT_WINDOW, ev, secs, ev.scheduled_ts - timedelta(minutes=cfg.pre_event_lockout_minutes), _scenarios(ev, hist), None, reasons, upcoming)
        return NewsState(NewsPhase.NONE, ev, secs, None, [], None, ["no material USD event inside the pre-event window"], upcoming)
    return NewsState(NewsPhase.NONE, None, None, None, [], None, ["no material USD events in scope"], upcoming)


def _build_reaction(ev: EconomicEvent, inputs: dict) -> dict:
    return {
        "event_id": ev.event_id,
        "event_name": ev.name,
        "category": ev.category,
        "release_ts": ev.scheduled_ts,
        "actual": ev.actual,
        "consensus": ev.consensus,
        "prior": ev.prior,
        "revised_prior": ev.revised_prior,
        "revision_flag": ev.revised_prior is not None and ev.prior is not None and ev.revised_prior != ev.prior,
        "surprise": ev.surprise,
        "standardised_surprise": ev.standardised_surprise,
        "standardisation_available": ev.standardised_surprise is not None,
        "higher_is_usd_positive": ev.higher_is_usd_positive,
        "dxy_response_sign": inputs.get("dxy_response_sign"),
        "us10y_response_sign": inputs.get("us10y_response_sign"),
        "gold_response_sign": inputs.get("gold_response_sign"),
        "gold_move_since_release": inputs.get("gold_move_since_release"),
        "spread_now": inputs.get("spread_now"),
        "verified": ev.verification == Verification.VERIFIED,
        "conflicting_components": inputs.get("conflicting_components", []),
    }
