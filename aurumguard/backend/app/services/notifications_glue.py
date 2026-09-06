"""Turns analysis events into notifications with the user's preferences applied."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..config import Settings
from ..core.news_state import NewsPhase, NewsState
from ..core.setup import Decision
from ..db.models import User, UserSettings
from ..notifications.service import NotificationService, Prefs, compose_decision, dedup_key_for_decision
from ..providers.base import PushProvider
from .bus import bus


class NotificationGlue:
    def __init__(self, db: Session, push: PushProvider, user: User, us: UserSettings, settings: Settings):
        self.svc = NotificationService(db, push)
        self.user = user
        self.tz = us.timezone
        self.prefs = Prefs.from_dict(us.notification_prefs)
        self.base_url = settings.cors_origins.split(",")[0].strip()

    def _send(self, kind: str, title: str, body: str, data: dict, key: str, now: datetime) -> int:
        rec = self.svc.notify(self.user.id, self.tz, self.prefs, kind, title, body, data, key, now)
        bus.publish(self.user.id, "notification", {"id": rec.id, "kind": rec.kind, "title": rec.title, "status": rec.delivery_status})
        return 1 if rec.created_at == now else 0

    def decision(self, d: Decision, prev_status: str | None, now: datetime) -> int:
        kind, title, body, data = compose_decision(d, self.tz, self.base_url)
        if prev_status in ("BUY_SETUP", "SELL_SETUP") and d.status.value not in ("BUY_SETUP", "SELL_SETUP"):
            kind = "SETUP_INVALIDATED" if d.status.value in ("NO_TRADE", "EVENT_LOCKOUT", "DATA_UNAVAILABLE") else "WAIT_UPDATED"
            title = f"{'[DEMO DATA] ' if d.demo_data else ''}XAU/USD setup no longer valid - {d.horizon}"
        if d.setup and d.setup.entry_confirmed and prev_status == "WAIT":
            kind = "SETUP_CONFIRMED"
        return self._send(kind, title, body, data, dedup_key_for_decision(d), now)

    def paper_event(self, ev: dict, now: datetime) -> int:
        p = ev["position"]
        kind = ev["kind"]
        if kind in ("OPENED", "CLOSED"):
            kind = "WAIT_UPDATED"
        title = f"Paper {p.direction} {p.strategy_id} {ev['kind'].replace('PAPER_', '')}: XAU/USD"
        body = f"Position {p.position_id} {p.direction} {p.lots_initial} lots @ {p.entry_price:.2f}; stop {p.stop:.2f}, TP1 {p.tp1:.2f}, TP2 {p.tp2:.2f}. Realised {p.realised_pnl_usd:+.2f} USD. tz {self.tz}."
        return self._send(kind, title, body, {"position_id": p.position_id, "url": f"{self.base_url}/paper"}, f"paper:{p.position_id}:{ev['kind']}", now)

    def news_transition(self, prev: str | None, news: NewsState, now: datetime) -> int:
        ev = news.event
        if ev is None:
            return 0
        n = 0
        name = f"{ev.name} ({ev.scheduled_ts.astimezone(__import__('zoneinfo').ZoneInfo(self.tz)).strftime('%a %H:%M %Z')})"
        if news.phase == NewsPhase.PRE_EVENT_WINDOW:
            n += self._send("EVENT_APPROACHING", f"USD event approaching: {ev.name}", f"{name}. Consensus {ev.consensus} {ev.unit}, prior {ev.prior}. Scenario table available in the app. Spreads and slippage usually widen around the release. tz {self.tz}.", {"event_id": ev.event_id, "url": f"{self.base_url}/calendar/{ev.event_id}"}, f"event:{ev.event_id}:approach", now)
        elif news.phase in (NewsPhase.PRE_EVENT_LOCKOUT, NewsPhase.RELEASE_LOCKOUT):
            n += self._send("EVENT_LOCKOUT_STARTED", f"Event lockout: {ev.name}", f"{name}. New setups are paused until the release is verified and the cooldown has passed. tz {self.tz}.", {"event_id": ev.event_id}, f"event:{ev.event_id}:lockout", now)
        elif news.phase in (NewsPhase.POST_RELEASE_CONFIRMATION, NewsPhase.NONE) and prev in ("RELEASE_LOCKOUT", "POST_RELEASE_COOLDOWN"):
            actual = f"actual {ev.actual} vs consensus {ev.consensus}" if ev.actual is not None else "actual pending"
            n += self._send("EVENT_LOCKOUT_ENDED", f"Event lockout ended: {ev.name}", f"{name}: {actual}. Analysis resumes; see the event page for the verified reaction. tz {self.tz}.", {"event_id": ev.event_id}, f"event:{ev.event_id}:ended", now)
        return n

    def risk_lock(self, locks: dict, now: datetime) -> int:
        active = [k.replace("_locked", "") for k, v in locks.items() if k.endswith("_locked") and v]
        return self._send("RISK_LIMIT_REACHED", "Risk limit reached: new setups paused", f"Locks active: {', '.join(active)}. {locks['details'].get('G10', '')}. No new paper entries until the lock clears. tz {self.tz}.", {"locks": active}, f"risklock:{','.join(active)}:{now.date()}", now)

    def friday_review(self, open_positions, cutoff: datetime, now: datetime) -> int:
        body = f"Friday cutoff at {cutoff.astimezone(__import__('zoneinfo').ZoneInfo(self.tz)).strftime('%H:%M %Z')}. Open paper positions: {len(open_positions)}. Weekly/swing positions will be closed automatically unless you have acknowledged weekend gap risk in Settings."
        return self._send("FRIDAY_REVIEW", "Friday weekly-position review", body, {"url": f"{self.base_url}/paper"}, f"friday:{cutoff.date()}:review", now)

    def friday_closed(self, closed: list[str], now: datetime) -> int:
        return self._send("FRIDAY_REVIEW", "Friday closure executed (paper)", f"Closed {len(closed)} weekly/swing paper position(s) at the cutoff: {', '.join(closed)}.", {"positions": closed}, f"friday:{now.date()}:closed", now)

    def weekend_gap_warning(self, positions, now: datetime, override: bool) -> int:
        return self._send("WEEKEND_GAP_WARNING", "Weekend gap risk on open positions", f"{len(positions)} position(s) remain open over the weekend{' under your recorded weekend-risk override' if override else ''}. Prices can reopen far from Friday's close; stops may fill with slippage.", {"positions": [p.position_id for p in positions]}, f"weekend:{now.date()}", now)
