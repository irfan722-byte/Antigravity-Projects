from .base import Strategy, StrategyContext, StrategyDefinition, StrategyProposal, load_definitions
from .breakout_retest import BreakoutRetest
from .post_news_confirmation import PostNewsConfirmation
from .pullback_continuation import PullbackContinuation
from .range_rejection import RangeRejection

IMPLEMENTATIONS: dict[str, type[Strategy]] = {
    "PBC-H1": PullbackContinuation,
    "BRT-M15": BreakoutRetest,
    "RRJ-H4": RangeRejection,
    "PNC-M15": PostNewsConfirmation,
}


def build_strategies(definitions: dict[str, StrategyDefinition] | None = None) -> dict[str, Strategy]:
    defs = definitions or load_definitions()
    out: dict[str, Strategy] = {}
    for sid, d in defs.items():
        cls = IMPLEMENTATIONS.get(sid)
        if cls is None:
            continue
        out[sid] = cls(d)
    return out


__all__ = ["Strategy", "StrategyContext", "StrategyDefinition", "StrategyProposal", "load_definitions", "build_strategies", "IMPLEMENTATIONS"]
