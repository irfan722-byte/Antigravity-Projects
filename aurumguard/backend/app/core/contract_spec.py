"""XAU/USD contract specifications.

Position sizing must use the *verified* specification of the venue the user
selects. Brokers differ on lot size, minimum size, step, tick value and
financing. The mock specification is clearly labelled and must not be used for
real sizing decisions.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractSpec:
    spec_id: str
    venue: str
    symbol: str
    contract_size_oz: float  # ounces per 1.0 lot
    min_lot: float
    lot_step: float
    max_lot: float
    tick_size: float
    quote_currency: str
    commission_per_lot_round_trip_usd: float
    financing_long_annual_pct: float | None  # estimate of overnight financing (negative = cost)
    financing_short_annual_pct: float | None
    verified: bool
    verification_source: str
    notes: str = ""

    @property
    def usd_per_lot_per_1usd_move(self) -> float:
        return self.contract_size_oz

    def to_dict(self) -> dict:
        return self.__dict__ | {"usd_per_lot_per_1usd_move": self.usd_per_lot_per_1usd_move}


MOCK_SPEC = ContractSpec(
    spec_id="mock-generic-100oz",
    venue="DEMO (mock broker)",
    symbol="XAUUSD",
    contract_size_oz=100.0,
    min_lot=0.01,
    lot_step=0.01,
    max_lot=20.0,
    tick_size=0.01,
    quote_currency="USD",
    commission_per_lot_round_trip_usd=0.0,
    financing_long_annual_pct=-4.5,
    financing_short_annual_pct=1.0,
    verified=False,
    verification_source="none - illustrative demo specification, not a broker document",
    notes="DEMO ONLY. Replace with a verified venue specification before any real use.",
)

SPECS: dict[str, ContractSpec] = {MOCK_SPEC.spec_id: MOCK_SPEC}


def get_spec(spec_id: str) -> ContractSpec:
    try:
        return SPECS[spec_id]
    except KeyError as exc:
        raise ValueError(f"unknown contract spec {spec_id}") from exc
