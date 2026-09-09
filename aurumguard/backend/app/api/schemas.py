from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    accept_disclosure: bool


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
    mfa_code: str | None = Field(default=None, max_length=8)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    onboarding_completed: bool


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=256)


class MfaVerifyIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class OnboardingIn(BaseModel):
    timezone: str = Field(max_length=64)
    account_currency: Literal["USD", "AED"]
    account_equity: float = Field(gt=0, le=1e8)
    risk_per_trade_pct: float | None = None
    friday_cutoff_local: str = Field(default="20:00", pattern=r"^\d{2}:\d{2}$")
    horizons: list[Literal["SCALP", "INTRADAY", "SWING", "WEEKLY"]] = ["INTRADAY", "SWING", "WEEKLY"]


class RiskLimitsIn(BaseModel):
    account_equity: float | None = Field(default=None, gt=0)
    account_currency: Literal["USD", "AED"] | None = None
    risk_per_trade_pct: float | None = None
    max_daily_loss_pct: float | None = None
    max_weekly_loss_pct: float | None = None
    max_monthly_drawdown_pct: float | None = None
    max_concurrent_positions: int | None = None
    max_aggregate_open_risk_pct: float | None = None
    max_trades_per_day: int | None = None
    max_consecutive_losses: int | None = None
    max_spread_usd: float | None = None
    max_expected_slippage_usd: float | None = None
    min_net_reward_to_risk: float | None = None
    event_risk_preference: Literal["avoid", "reduced", "allow_post_confirmation"] | None = None
    daily_lockout_enabled: bool | None = None
    weekly_lockout_enabled: bool | None = None
    friday_cutoff_local: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    friday_auto_close_paper: bool | None = None


class SettingsIn(BaseModel):
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=8)
    theme: Literal["light", "dark", "system"] | None = None
    notification_prefs: dict | None = None
    horizons_enabled: dict | None = None
    weekend_risk_acknowledged: bool | None = None

    @field_validator("notification_prefs")
    @classmethod
    def _prefs(cls, v):  # type: ignore[no-untyped-def]
        if v is None:
            return v
        allowed = {"enabled", "quiet_start", "quiet_end", "quiet_allow_high", "max_per_hour", "kinds_disabled", "channels", "auto_paper_trade"}
        bad = set(v) - allowed
        if bad:
            raise ValueError(f"unknown preference keys: {sorted(bad)}")
        return v


class PositionSizeIn(BaseModel):
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    direction: Literal["BUY", "SELL"]
    spread: float = Field(ge=0, le=10)
    slippage: float = Field(ge=0, le=5)
    risk_pct: float | None = Field(default=None, gt=0, le=5)
    equity: float | None = Field(default=None, gt=0)
    tp1: float | None = None
    tp2: float | None = None


class PaperOrderIn(BaseModel):
    decision_id: str = Field(max_length=64)


class PaperCloseIn(BaseModel):
    position_id: str = Field(max_length=64)
    reason: str = Field(default="manual", max_length=40)


class BacktestIn(BaseModel):
    strategy_id: str = Field(max_length=32)
    start: str
    end: str
    kind: Literal["backtest", "validation"] = "backtest"
    spread_multiplier: float = Field(default=1.0, ge=0.0, le=5.0)
    slippage_multiplier: float = Field(default=1.0, ge=0.0, le=5.0)
    params_override: dict = Field(default_factory=dict)


class StrategyActionIn(BaseModel):
    action: Literal["approve", "suspend", "reactivate", "retire", "record_validation"]
    note: str = Field(default="", max_length=2000)
    threshold: float | None = Field(default=None, ge=0, le=100)
    run_id: str | None = None


class PushSubscribeIn(BaseModel):
    subscription: dict
    user_agent: str = Field(default="", max_length=255)


class DeleteAccountIn(BaseModel):
    password: str = Field(max_length=128)
    confirm: Literal["DELETE MY ACCOUNT"]
