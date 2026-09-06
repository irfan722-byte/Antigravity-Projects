"""Database schema. Every timestamp column is timezone-aware UTC.

Append-only tables: audit_log, decisions, notifications, paper_events. Rows in
those tables are never updated after insert (enforced in the service layer and
by the absence of update paths in the API)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _now() -> datetime:

    return datetime.now(tz=UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # user | admin
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    disclosure_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    settings: Mapped[UserSettings] = relationship(back_populates="user", uselist=False)


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Dubai")
    account_currency: Mapped[str] = mapped_column(String(3), default="USD")
    contract_spec_id: Mapped[str] = mapped_column(String(64), default="mock-generic-100oz")
    risk_limits: Mapped[dict] = mapped_column(JSON, default=dict)  # RiskLimits.to_dict()
    notification_prefs: Mapped[dict] = mapped_column(JSON, default=dict)
    horizons_enabled: Mapped[dict] = mapped_column(JSON, default=dict)
    locale: Mapped[str] = mapped_column(String(8), default="en")
    theme: Mapped[str] = mapped_column(String(8), default="system")
    weekend_risk_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="settings")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StrategyRecord(Base):
    """Registry state that the admin workflow controls (status, approvals, validation)."""

    __tablename__ = "strategies"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    version: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="RESEARCH")  # RESEARCH|APPROVED|SUSPENDED|RETIRED
    production_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    backtest_results: Mapped[dict] = mapped_column(JSON, default=dict)
    paper_results: Mapped[dict] = mapped_column(JSON, default=dict)
    approval_history: Mapped[list] = mapped_column(JSON, default=list)
    change_log: Mapped[list] = mapped_column(JSON, default=list)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class DecisionRecord(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    horizon: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    strategy_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    strategy_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reason: Mapped[str] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    demo_data: Mapped[bool] = mapped_column(Boolean, default=True)
    setup: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_decisions_user_horizon_asof", "user_id", "horizon", "as_of"),)


class DecisionOutcome(Base):
    """Recorded separately, after expiry. Never merged into the decision row."""

    __tablename__ = "decision_outcomes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), unique=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    outcome: Mapped[str] = mapped_column(String(24))  # TP1|TP2|STOP|EXPIRED|INVALIDATED|NOT_TAKEN
    max_favourable_excursion: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_adverse_excursion: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class PaperOrderRecord(Base):
    __tablename__ = "paper_orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    decision_id: Mapped[str | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    strategy_id: Mapped[str] = mapped_column(String(32))
    horizon: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(4))
    order_type: Mapped[str] = mapped_column(String(8))
    lots: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PaperPositionRecord(Base):
    __tablename__ = "paper_positions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("paper_orders.id"))
    decision_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    strategy_version: Mapped[str] = mapped_column(String(16))
    horizon: Mapped[str] = mapped_column(String(16), index=True)
    direction: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(8), index=True)
    entry_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    exit_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_price: Mapped[float] = mapped_column(Float)
    lots_initial: Mapped[float] = mapped_column(Float)
    lots_open: Mapped[float] = mapped_column(Float)
    stop: Mapped[float] = mapped_column(Float)
    initial_stop: Mapped[float] = mapped_column(Float)
    tp1: Mapped[float] = mapped_column(Float)
    tp2: Mapped[float] = mapped_column(Float)
    risk_usd: Mapped[float] = mapped_column(Float)
    realised_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    exit_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # fills, modifications, meta
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PaperEventRecord(Base):
    __tablename__ = "paper_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    ref_id: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class NotificationRecord(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[str] = mapped_column(String(8))
    dedup_key: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    delivery_status: Mapped[str] = mapped_column(String(16), default="QUEUED")  # QUEUED|SENT|FAILED|THROTTLED|QUIET_HOURS|DEDUPED
    delivery_detail: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "dedup_key", name="uq_notification_dedup"),)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint_hash: Mapped[str] = mapped_column(String(128), unique=True)
    subscription: Mapped[dict] = mapped_column(JSON)
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    """Append-only. Hash-chained: each row stores the hash of the previous row."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    actor: Mapped[str] = mapped_column(String(64), index=True)  # user id | system | scheduler
    action: Mapped[str] = mapped_column(String(64), index=True)
    subject: Mapped[str] = mapped_column(String(128), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    row_hash: Mapped[str] = mapped_column(String(64), default="")


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    strategy_version: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))  # backtest | validation
    label: Mapped[str] = mapped_column(String(32))
    data_label: Mapped[str] = mapped_column(String(16))
    config_hash: Mapped[str] = mapped_column(String(32))
    trades_hash: Mapped[str] = mapped_column(String(32), default="")
    requested_by: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EconomicEventRecord(Base):
    """Point-in-time store of calendar events with revision history."""

    __tablename__ = "economic_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    scheduled_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingested_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (Index("ix_econ_event_ingest", "event_id", "ingested_ts"),)


class ProviderHealthRecord(Base):
    __tablename__ = "provider_health"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    payload: Mapped[list] = mapped_column(JSON)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    users: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    data_status: Mapped[str] = mapped_column(String(16), default="VALID")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
