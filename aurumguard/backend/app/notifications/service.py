"""Notification service: composes user-facing messages, applies deduplication,
throttling, quiet hours and priority, records delivery status and retries.

Language policy: factual, no urgency words, no profit language. The composer
is the only place notification copy is produced."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from ..core.setup import Decision, DecisionStatus
from ..core.timeutil import parse_local_time, resolve_tz
from ..db.models import NotificationRecord, PushSubscription
from ..providers.base import PushMessage, PushProvider

UTC = UTC

KINDS = {
    "DEVELOPING_SETUP": "normal",
    "BUY_SETUP": "high",
    "SELL_SETUP": "high",
    "WAIT_UPDATED": "low",
    "SETUP_CONFIRMED": "high",
    "SETUP_INVALIDATED": "normal",
    "SETUP_EXPIRED": "low",
    "PAPER_TP1": "normal",
    "PAPER_TP2": "normal",
    "PAPER_STOP": "normal",
    "EVENT_APPROACHING": "normal",
    "EVENT_LOCKOUT_STARTED": "normal",
    "EVENT_LOCKOUT_ENDED": "low",
    "SPREAD_TOO_HIGH": "low",
    "DATA_DEGRADED": "high",
    "RISK_LIMIT_REACHED": "high",
    "STRATEGY_SUSPENDED": "high",
    "FRIDAY_REVIEW": "high",
    "WEEKEND_GAP_WARNING": "normal",
}
BANNED_WORDS = ("guaranteed", "risk-free", "can't lose", "sure thing", "act now", "don't miss", "last chance", "hurry")


@dataclass
class Prefs:
    enabled: bool = True
    quiet_start: str = "23:00"
    quiet_end: str = "07:00"
    quiet_allow_high: bool = True
    max_per_hour: int = 12
    kinds_disabled: tuple[str, ...] = ()
    channels: tuple[str, ...] = ("push", "inapp")

    @classmethod
    def from_dict(cls, d: dict | None) -> Prefs:
        d = d or {}
        return cls(d.get("enabled", True), d.get("quiet_start", "23:00"), d.get("quiet_end", "07:00"), d.get("quiet_allow_high", True), int(d.get("max_per_hour", 12)), tuple(d.get("kinds_disabled", [])), tuple(d.get("channels", ["push", "inapp"])))


def in_quiet_hours(now: datetime, tz_name: str, start: str, end: str) -> bool:
    local = now.astimezone(resolve_tz(tz_name)).time()
    s, e = parse_local_time(start), parse_local_time(end)
    if s <= e:
        return s <= local < e
    return local >= s or local < e


def _fmt_local(ts: datetime | None, tz_name: str) -> str:
    if ts is None:
        return "n/a"
    return ts.astimezone(resolve_tz(tz_name)).strftime("%Y-%m-%d %H:%M %Z")


def compose_decision(d: Decision, tz_name: str, base_url: str = "") -> tuple[str, str, str, dict]:
    """Return (kind, title, body, data) for a decision notification."""
    demo = "[DEMO DATA] " if d.demo_data else ""
    link = f"{base_url}/setups/{d.decision_id}"
    if d.setup:
        s = d.setup
        kind = "BUY_SETUP" if d.status == DecisionStatus.BUY_SETUP else "SELL_SETUP"
        tps = " | ".join(f"{t.label} {t.price:.2f} (net R:R {t.net_reward_to_risk:.2f})" for t in s.targets if t.net_reward_to_risk is not None)
        title = f"{demo}XAU/USD {s.direction} SETUP - {s.horizon} - {s.strategy_name}"
        body = (
            f"Entry {s.entry_zone_low:.2f}-{s.entry_zone_high:.2f} ({'confirmation still required' if s.entry_confirmation_required and not s.entry_confirmed else 'trigger confirmed'})\n"
            f"Stop {s.stop_loss:.2f} | {tps}\n"
            f"Expires {_fmt_local(s.expiry, tz_name)}\n"
            f"Why: {s.decision_reason}\n"
            f"Main risk: {(s.contradictory_evidence[0]['description'] if s.contradictory_evidence else 'no contradicting evidence recorded; setup remains uncertain')}\n"
            f"Data {_fmt_local(s.price_timestamp, tz_name)} ({s.data_provider}) | tz {tz_name}\n"
            f"Evidence: {link}"
        )
        data = {"decision_id": d.decision_id, "horizon": s.horizon, "strategy": s.strategy_id, "direction": s.direction, "url": link}
        return kind, title, body, data
    if d.status == DecisionStatus.WAIT:
        return "DEVELOPING_SETUP", f"{demo}XAU/USD developing setup - {d.horizon}", f"{d.reason}\nData {_fmt_local(d.as_of, tz_name)} | tz {tz_name}\nEvidence: {link}", {"decision_id": d.decision_id, "url": link}
    if d.status == DecisionStatus.EVENT_LOCKOUT:
        return "EVENT_LOCKOUT_STARTED", f"{demo}XAU/USD event lockout - {d.horizon}", f"{d.reason}\nData {_fmt_local(d.as_of, tz_name)} | tz {tz_name}", {"decision_id": d.decision_id, "url": link}
    if d.status == DecisionStatus.DATA_UNAVAILABLE:
        return "DATA_DEGRADED", f"{demo}XAU/USD data unavailable - {d.horizon}", f"{d.reason}\nData {_fmt_local(d.as_of, tz_name)} | tz {tz_name}", {"decision_id": d.decision_id, "url": link}
    return "WAIT_UPDATED", f"{demo}XAU/USD {d.status.value} - {d.horizon}", f"{d.reason}\nData {_fmt_local(d.as_of, tz_name)} | tz {tz_name}", {"decision_id": d.decision_id, "url": link}


def check_language(text: str) -> list[str]:
    low = text.lower()
    return [w for w in BANNED_WORDS if w in low]


class NotificationService:
    def __init__(self, db: Session, push: PushProvider):
        self.db = db
        self.push = push

    def notify(self, user_id: str, tz_name: str, prefs: Prefs, kind: str, title: str, body: str, data: dict, dedup_key: str, now: datetime | None = None) -> NotificationRecord:
        now = now or datetime.now(tz=UTC)
        priority = KINDS.get(kind, "normal")
        bad = check_language(title + " " + body)
        if bad:
            raise ValueError(f"notification copy violates language policy: {bad}")
        existing = self.db.query(NotificationRecord).filter(NotificationRecord.user_id == user_id, NotificationRecord.dedup_key == dedup_key).one_or_none()
        if existing:
            return existing
        rec = NotificationRecord(id=uuid.uuid4().hex[:24], user_id=user_id, kind=kind, priority=priority, dedup_key=dedup_key, title=title, body=body, payload=data | {"tz": tz_name, "created_local": _fmt_local(now, tz_name)}, created_at=now)
        if not prefs.enabled or kind in prefs.kinds_disabled:
            rec.delivery_status = "SUPPRESSED"
            rec.delivery_detail = "disabled by user preference"
        elif in_quiet_hours(now, tz_name, prefs.quiet_start, prefs.quiet_end) and not (priority == "high" and prefs.quiet_allow_high):
            rec.delivery_status = "QUIET_HOURS"
            rec.delivery_detail = "held: quiet hours"
        else:
            recent = self.db.query(NotificationRecord).filter(NotificationRecord.user_id == user_id, NotificationRecord.created_at >= now - timedelta(hours=1), NotificationRecord.delivery_status.in_(["SENT", "QUEUED"])).count()
            if recent >= prefs.max_per_hour and priority != "high":
                rec.delivery_status = "THROTTLED"
                rec.delivery_detail = f"held: {recent} notifications in the last hour"
        self.db.add(rec)
        self.db.commit()
        if rec.delivery_status == "QUEUED" and "push" in prefs.channels:
            self.deliver(rec)
        return rec

    def deliver(self, rec: NotificationRecord, max_attempts: int = 3) -> None:
        subs = self.db.query(PushSubscription).filter(PushSubscription.user_id == rec.user_id, PushSubscription.active.is_(True)).all()
        if not subs:
            rec.delivery_status = "SENT"
            rec.delivery_detail = "in-app only (no push subscription)"
            self.db.commit()
            return
        ok_any = False
        details = []
        msg = PushMessage(rec.title, rec.body, rec.payload, rec.priority, tag=rec.dedup_key[:60])
        for sub in subs:
            res = None
            for _attempt in range(max_attempts):
                res = self.push.send(sub.subscription, msg)
                rec.attempts += 1
                if res.ok:
                    break
            if res and res.ok:
                ok_any = True
                sub.last_success = res.ts
                sub.failures = 0
            else:
                sub.failures += 1
                if sub.failures >= 5:
                    sub.active = False
            details.append(f"{sub.id[:6]}: {res.detail if res else 'no attempt'}")
        rec.delivery_status = "SENT" if ok_any else "FAILED"
        rec.delivery_detail = "; ".join(details)
        self.db.commit()

    def release_quiet_hours(self, user_id: str, tz_name: str, prefs: Prefs, now: datetime) -> int:
        """Deliver held notifications once quiet hours end."""
        if in_quiet_hours(now, tz_name, prefs.quiet_start, prefs.quiet_end):
            return 0
        held = self.db.query(NotificationRecord).filter(NotificationRecord.user_id == user_id, NotificationRecord.delivery_status == "QUIET_HOURS").all()
        n = 0
        for rec in held:
            if now - rec.created_at.replace(tzinfo=UTC) > timedelta(hours=12):
                rec.delivery_status = "EXPIRED"
                rec.delivery_detail = "held past usefulness"
                continue
            rec.delivery_status = "QUEUED"
            self.deliver(rec)
            n += 1
        self.db.commit()
        return n


def dedup_key_for_decision(d: Decision) -> str:
    base = f"{d.horizon}:{d.status.value}:{d.strategy_id}:{d.setup.direction if d.setup else ''}:{round(d.setup.stop_loss, 1) if d.setup else ''}:{d.as_of.strftime('%Y-%m-%d')}"
    return hashlib.sha256(base.encode()).hexdigest()[:40]
