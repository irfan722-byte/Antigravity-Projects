"""Paper-trading engine.

Deterministic, storage-agnostic simulation. The service layer persists orders,
positions and the event log; this module only knows prices as they arrive, in
order. It never looks at a later candle to improve an earlier fill.

Execution rules (documented in docs/17-backtesting-methodology.md):
- Longs fill at the ask, exit at the bid; shorts mirror. Spread comes from the
  quote/candle in force at the time.
- Slippage is added adversely to every fill.
- Market orders fill immediately on the next quote. Limit orders fill when the
  relevant side touches the limit price. Stop orders fill when the relevant
  side trades through the stop price (with slippage).
- Stops/targets are evaluated on each closed M1 candle (or coarser if that is
  all the caller has, which the result labels). If stop and target are both
  inside one candle's range and no tick sequence exists, the stop is assumed to
  be hit first (conservative) and the fill is labelled CONSERVATIVE_SAME_BAR.
- A bar that opens beyond the stop (gap) fills at the open plus slippage.
- Partial fills: lots above ``max_fill_lots`` fill in pieces on successive quotes.
- Fills are rejected when the spread exceeds the order's max_spread.
- Time stop, setup expiry, Friday closure and lockout closures are explicit
  calls made by the service with the current quote.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..core.candles import Candle, Quote
from ..core.contract_spec import ContractSpec
from ..core.timeutil import ensure_utc


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass
class Fill:
    ts: datetime
    price: float
    lots: float
    kind: str  # entry | tp1 | tp2 | tp3 | stop | time_stop | manual | friday_close | lockout_close | expiry_close
    label: str = ""
    slippage: float = 0.0
    spread: float = 0.0


@dataclass
class PaperOrder:
    order_id: str
    decision_id: str | None
    strategy_id: str
    strategy_version: str
    horizon: str
    direction: str  # BUY | SELL
    order_type: OrderType
    lots: float
    stop: float
    tp1: float
    tp2: float
    expiry: datetime
    max_holding_until: datetime | None
    max_spread: float
    created_at: datetime
    limit_price: float | None = None
    tp3: float | None = None
    partial_close_at_tp1_pct: float = 50.0
    move_to_breakeven_after_tp1: bool = False
    risk_usd: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    filled_lots: float = 0.0
    reject_reason: str | None = None
    user_id: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class PaperPosition:
    position_id: str
    order_id: str
    decision_id: str | None
    user_id: str
    strategy_id: str
    strategy_version: str
    horizon: str
    direction: str
    lots_initial: float
    lots_open: float
    entry_price: float
    entry_ts: datetime
    stop: float
    initial_stop: float
    tp1: float
    tp2: float
    tp3: float | None
    max_holding_until: datetime | None
    partial_close_at_tp1_pct: float
    move_to_breakeven_after_tp1: bool
    risk_usd: float
    status: PositionStatus = PositionStatus.OPEN
    tp1_hit: bool = False
    tp2_hit: bool = False
    realised_pnl_usd: float = 0.0
    fills: list[Fill] = field(default_factory=list)
    exit_reason: str | None = None
    exit_ts: datetime | None = None
    modifications: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def r_multiple(self) -> float | None:
        if self.risk_usd <= 0 or self.status != PositionStatus.CLOSED:
            return None
        return self.realised_pnl_usd / self.risk_usd


@dataclass
class PaperEvent:
    ts: datetime
    kind: str
    ref_id: str
    detail: dict


@dataclass
class SlippageParams:
    entry: float = 0.10
    exit: float = 0.10
    gap_extra: float = 0.15


class PaperEngine:
    def __init__(self, spec: ContractSpec, slippage: SlippageParams | None = None, max_fill_lots: float = 5.0, conservative_same_bar: bool = True):
        self.spec = spec
        self.slip = slippage or SlippageParams()
        self.max_fill_lots = max_fill_lots
        self.conservative_same_bar = conservative_same_bar
        self.orders: dict[str, PaperOrder] = {}
        self.positions: dict[str, PaperPosition] = {}
        self.events: list[PaperEvent] = []
        self._last_ts: datetime | None = None
        self._seq = 0

    # ------------------------------------------------------------ utils --
    def _tick(self, ts: datetime) -> None:
        ts = ensure_utc(ts)
        if self._last_ts is not None and ts < self._last_ts:
            raise ValueError(f"paper engine received out-of-order time {ts.isoformat()} < {self._last_ts.isoformat()}")
        self._last_ts = ts

    def _log(self, ts: datetime, event: str, ref: str, **detail) -> None:
        self.events.append(PaperEvent(ts, event, ref, detail))

    def _pnl(self, pos: PaperPosition, exit_price: float, lots: float) -> float:
        sign = 1 if pos.direction == "BUY" else -1
        return sign * (exit_price - pos.entry_price) * lots * self.spec.contract_size_oz - self.spec.commission_per_lot_round_trip_usd * lots

    def new_id(self, prefix: str) -> str:
        """Deterministic per-engine sequence ids (reproducible backtests). The service layer
        prefixes them with the user id when persisting."""
        self._seq += 1
        return f"{prefix}_{self._seq:06d}"

    # ---------------------------------------------------------- orders ---
    def submit(self, order: PaperOrder) -> PaperOrder:
        self._tick(order.created_at)
        if order.lots < self.spec.min_lot:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"lots {order.lots} below minimum {self.spec.min_lot}"
        elif order.lots > self.spec.max_lot:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"lots {order.lots} above maximum {self.spec.max_lot}"
        elif (order.direction == "BUY" and not (order.stop < order.tp1 < order.tp2)) or (order.direction == "SELL" and not (order.stop > order.tp1 > order.tp2)):
            order.status = OrderStatus.REJECTED
            order.reject_reason = "stop/tp ordering invalid"
        elif order.order_type != OrderType.MARKET and order.limit_price is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "limit/stop order needs a price"
        self.orders[order.order_id] = order
        self._log(order.created_at, "order_submitted" if order.status == OrderStatus.PENDING else "order_rejected", order.order_id, status=order.status.value, reason=order.reject_reason, direction=order.direction, lots=order.lots)
        return order

    def cancel(self, order_id: str, now: datetime, reason: str) -> None:
        o = self.orders[order_id]
        if o.status in (OrderStatus.PENDING, OrderStatus.PARTIAL):
            o.status = OrderStatus.CANCELLED
            self._log(now, "order_cancelled", order_id, reason=reason)

    def on_quote(self, q: Quote) -> list[PaperPosition]:
        """Process pending orders against a live quote. Returns newly created positions."""
        self._tick(q.ts)
        created: list[PaperPosition] = []
        for o in list(self.orders.values()):
            if o.status not in (OrderStatus.PENDING, OrderStatus.PARTIAL):
                continue
            if q.ts >= o.expiry:
                o.status = OrderStatus.EXPIRED
                self._log(q.ts, "order_expired", o.order_id)
                continue
            if q.spread > o.max_spread:
                o.status = OrderStatus.REJECTED
                o.reject_reason = f"spread {q.spread:.2f} > max {o.max_spread:.2f}"
                self._log(q.ts, "order_rejected", o.order_id, reason=o.reject_reason)
                continue
            touch = q.ask if o.direction == "BUY" else q.bid
            fill_price: float | None = None
            if o.order_type == OrderType.MARKET:
                fill_price = touch + self.slip.entry if o.direction == "BUY" else touch - self.slip.entry
            elif o.order_type == OrderType.LIMIT:
                if (o.direction == "BUY" and touch <= o.limit_price) or (o.direction == "SELL" and touch >= o.limit_price):
                    fill_price = o.limit_price  # limit orders do not slip beyond their price
            elif o.order_type == OrderType.STOP:
                if (o.direction == "BUY" and touch >= o.limit_price) or (o.direction == "SELL" and touch <= o.limit_price):
                    fill_price = touch + self.slip.entry if o.direction == "BUY" else touch - self.slip.entry
            if fill_price is None:
                continue
            # entering beyond the stop is nonsensical: reject rather than fill
            if (o.direction == "BUY" and fill_price <= o.stop) or (o.direction == "SELL" and fill_price >= o.stop):
                o.status = OrderStatus.REJECTED
                o.reject_reason = "price already through the stop at fill time"
                self._log(q.ts, "order_rejected", o.order_id, reason=o.reject_reason)
                continue
            remaining = round(o.lots - o.filled_lots, 6)
            lots = min(remaining, self.max_fill_lots)
            o.filled_lots = round(o.filled_lots + lots, 6)
            partial = o.filled_lots < o.lots
            o.status = OrderStatus.PARTIAL if partial else OrderStatus.FILLED
            pos = PaperPosition(
                position_id=self.new_id("pos"), order_id=o.order_id, decision_id=o.decision_id, user_id=o.user_id, strategy_id=o.strategy_id, strategy_version=o.strategy_version, horizon=o.horizon,
                direction=o.direction, lots_initial=lots, lots_open=lots, entry_price=round(fill_price, 2), entry_ts=q.ts, stop=o.stop, initial_stop=o.stop, tp1=o.tp1, tp2=o.tp2, tp3=o.tp3,
                max_holding_until=o.max_holding_until, partial_close_at_tp1_pct=o.partial_close_at_tp1_pct, move_to_breakeven_after_tp1=o.move_to_breakeven_after_tp1, risk_usd=o.risk_usd * lots / o.lots, meta=dict(o.meta),
            )
            pos.fills.append(Fill(q.ts, pos.entry_price, lots, "entry", "PARTIAL" if partial else "", self.slip.entry if o.order_type != OrderType.LIMIT else 0.0, q.spread))
            self.positions[pos.position_id] = pos
            created.append(pos)
            self._log(q.ts, "position_opened", pos.position_id, order_id=o.order_id, price=pos.entry_price, lots=lots, partial=partial, spread=q.spread)
        return created

    # -------------------------------------------------------- positions --
    def _close(self, pos: PaperPosition, ts: datetime, price: float, lots: float, kind: str, label: str = "", slippage: float = 0.0, spread: float = 0.0) -> None:
        lots = min(lots, pos.lots_open)
        if lots <= 0:
            return
        pnl = self._pnl(pos, price, lots)
        pos.realised_pnl_usd += pnl
        pos.lots_open = round(pos.lots_open - lots, 6)
        pos.fills.append(Fill(ts, round(price, 2), lots, kind, label, slippage, spread))
        self._log(ts, "position_fill", pos.position_id, kind=kind, label=label, price=round(price, 2), lots=lots, pnl=round(pnl, 2))
        if pos.lots_open <= 1e-9:
            pos.status = PositionStatus.CLOSED
            pos.exit_reason = kind
            pos.exit_ts = ts
            self._log(ts, "position_closed", pos.position_id, reason=kind, realised=round(pos.realised_pnl_usd, 2), r=round(pos.r_multiple or 0, 3))

    def on_candle(self, c: Candle, default_spread: float = 0.3) -> None:
        """Evaluate stops/targets for open positions on one *closed* candle (mid prices)."""
        self._tick(c.end_ts)
        spread = c.spread_close if c.spread_close is not None else default_spread
        half = spread / 2
        for pos in list(self.positions.values()):
            if pos.status != PositionStatus.OPEN or c.ts < pos.entry_ts:
                continue
            # time stop
            if pos.max_holding_until and c.end_ts >= pos.max_holding_until:
                exit_px = (c.close - half) if pos.direction == "BUY" else (c.close + half)
                self._close(pos, c.end_ts, exit_px - self.slip.exit if pos.direction == "BUY" else exit_px + self.slip.exit, pos.lots_open, "time_stop", "", self.slip.exit, spread)
                continue
            if pos.direction == "BUY":
                bid_open, bid_high, bid_low = c.open - half, c.high - half, c.low - half
                stop_hit = bid_low <= pos.stop
                gap = bid_open <= pos.stop
                tp1_hit = (not pos.tp1_hit) and bid_high >= pos.tp1
                tp2_hit = bid_high >= pos.tp2
                tp3_hit = pos.tp3 is not None and bid_high >= pos.tp3
            else:
                ask_open, ask_high, ask_low = c.open + half, c.high + half, c.low + half
                stop_hit = ask_high >= pos.stop
                gap = ask_open >= pos.stop
                tp1_hit = (not pos.tp1_hit) and ask_low <= pos.tp1
                tp2_hit = ask_low <= pos.tp2
                tp3_hit = pos.tp3 is not None and ask_low <= pos.tp3
            if stop_hit and (tp1_hit or tp2_hit):
                if self.conservative_same_bar:
                    self._stop_out(pos, c, gap, spread, label="CONSERVATIVE_SAME_BAR")
                    continue
            if stop_hit:
                self._stop_out(pos, c, gap, spread)
                continue
            if tp1_hit:
                pos.tp1_hit = True
                lots = round(pos.lots_initial * pos.partial_close_at_tp1_pct / 100.0, 6)
                lots = max(min(lots, pos.lots_open), self.spec.min_lot if pos.lots_open > self.spec.min_lot else pos.lots_open)
                self._close(pos, c.end_ts, pos.tp1, lots, "tp1", "", 0.0, spread)
                if pos.status == PositionStatus.OPEN and pos.move_to_breakeven_after_tp1:
                    old = pos.stop
                    pos.stop = pos.entry_price
                    pos.modifications.append({"ts": c.end_ts.isoformat(), "field": "stop", "from": old, "to": pos.stop, "reason": "breakeven after TP1 (strategy rule)"})
                    self._log(c.end_ts, "stop_modified", pos.position_id, **pos.modifications[-1])
            if pos.status == PositionStatus.OPEN and tp2_hit:
                pos.tp2_hit = True
                if pos.tp3 is None:
                    self._close(pos, c.end_ts, pos.tp2, pos.lots_open, "tp2", "", 0.0, spread)
                else:
                    self._close(pos, c.end_ts, pos.tp2, round(pos.lots_open / 2, 6) if pos.lots_open / 2 >= self.spec.min_lot else pos.lots_open, "tp2", "", 0.0, spread)
            if pos.status == PositionStatus.OPEN and tp3_hit:
                self._close(pos, c.end_ts, pos.tp3, pos.lots_open, "tp3", "", 0.0, spread)  # type: ignore[arg-type]

    def _stop_out(self, pos: PaperPosition, c: Candle, gap: bool, spread: float, label: str = "") -> None:
        half = spread / 2
        if gap:
            px = (c.open - half) if pos.direction == "BUY" else (c.open + half)
            slip = self.slip.exit + self.slip.gap_extra
            label = (label + " " if label else "") + "GAP_THROUGH_STOP"
        else:
            px = pos.stop
            slip = self.slip.exit
        px = px - slip if pos.direction == "BUY" else px + slip
        self._close(pos, c.end_ts, px, pos.lots_open, "stop", label.strip(), slip, spread)

    def close_position(self, position_id: str, q: Quote, kind: str, label: str = "") -> None:
        self._tick(q.ts)
        pos = self.positions[position_id]
        if pos.status != PositionStatus.OPEN:
            return
        px = (q.bid - self.slip.exit) if pos.direction == "BUY" else (q.ask + self.slip.exit)
        self._close(pos, q.ts, px, pos.lots_open, kind, label, self.slip.exit, q.spread)

    def close_all(self, q: Quote, kind: str, label: str = "") -> list[str]:
        closed = []
        for pid, pos in list(self.positions.items()):
            if pos.status == PositionStatus.OPEN:
                self.close_position(pid, q, kind, label)
                closed.append(pid)
        for o in self.orders.values():
            if o.status in (OrderStatus.PENDING, OrderStatus.PARTIAL):
                self.cancel(o.order_id, q.ts, kind)
        return closed

    # --------------------------------------------------------- reporting --
    def open_positions(self) -> list[PaperPosition]:
        return [p for p in self.positions.values() if p.status == PositionStatus.OPEN]

    def unrealised(self, q: Quote) -> float:
        total = 0.0
        for p in self.open_positions():
            px = q.bid if p.direction == "BUY" else q.ask
            total += self._pnl(p, px, p.lots_open) + self.spec.commission_per_lot_round_trip_usd * p.lots_open
        return total

    def realised(self) -> float:
        return sum(p.realised_pnl_usd for p in self.positions.values())

    def open_risk_usd(self) -> float:
        """Risk still at stake on open positions given *current* stops (never wider than initial)."""
        total = 0.0
        for p in self.open_positions():
            sign = 1 if p.direction == "BUY" else -1
            total += max(0.0, sign * (p.entry_price - p.stop)) * p.lots_open * self.spec.contract_size_oz
        return total
