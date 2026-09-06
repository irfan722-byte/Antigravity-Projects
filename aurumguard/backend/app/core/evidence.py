"""Evidence families and the explainable scoring engine.

Score is *one* input to the decision engine; it never creates a signal alone.
Correlated evidence within a configured group is collapsed to the strongest
single item so that, e.g., RSI and stochastic cannot double count.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Sequence

from ..config import load_json_config


class Family(str, Enum):
    TECHNICAL = "technical"
    STRUCTURE = "structure"
    LIQUIDITY_EXECUTION = "liquidity_volatility_execution"
    VOLATILITY = "volatility"
    INTERMARKET = "intermarket_flow"
    MACRO = "macro"
    POSITIONING = "positioning"
    NEWS_EVENT = "news_event"
    STRATEGY_HISTORY = "strategy_reliability"
    RISK_COST = "risk_cost"


@dataclass(frozen=True)
class Evidence:
    family: Family
    key: str
    direction: int  # +1 bullish, -1 bearish, 0 neutral/informational
    strength: float  # 0..1
    description: str
    source: str
    ts: datetime | None = None
    correlated_group: str | None = None
    available: bool = True

    def to_dict(self) -> dict:
        return {
            "family": self.family.value,
            "key": self.key,
            "direction": self.direction,
            "strength": round(self.strength, 3),
            "description": self.description,
            "source": self.source,
            "ts": self.ts.isoformat() if self.ts else None,
            "correlated_group": self.correlated_group,
            "available": self.available,
        }


@dataclass
class FamilyScore:
    family: Family
    weight: float
    net: float  # -1..+1 after de-duplication
    items_used: list[Evidence]
    items_collapsed: list[Evidence]
    contribution: float  # weight * net * direction sign of proposal


@dataclass
class ScoreBreakdown:
    direction: int
    score: float  # 0..100 in favour of ``direction``
    threshold: float
    families: list[FamilyScore]
    supporting: list[Evidence]
    contradicting: list[Evidence]
    independent_families_supporting: int
    dominant_family_share: float
    config_version: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "direction": self.direction,
            "score": round(self.score, 1),
            "research_threshold": self.threshold,
            "config_version": self.config_version,
            "independent_families_supporting": self.independent_families_supporting,
            "dominant_family_share": round(self.dominant_family_share, 3),
            "families": [
                {
                    "family": f.family.value,
                    "weight": f.weight,
                    "net": round(f.net, 3),
                    "contribution": round(f.contribution, 3),
                    "used": [e.key for e in f.items_used],
                    "collapsed_as_correlated": [e.key for e in f.items_collapsed],
                }
                for f in self.families
            ],
            "supporting": [e.to_dict() for e in self.supporting],
            "contradicting": [e.to_dict() for e in self.contradicting],
            "notes": self.notes,
        }


def _group_of(key: str, groups: Sequence[Sequence[str]]) -> str | None:
    for g in groups:
        if key in g:
            return "|".join(g)
    return None


def score_evidence(items: Sequence[Evidence], direction: int, config: dict | None = None) -> ScoreBreakdown:
    """Compute a 0..100 score for a proposed direction (+1 buy / -1 sell)."""
    cfg = config or load_json_config("scoring_config.json")
    weights: dict[str, float] = cfg["family_weights"]
    groups = cfg.get("correlated_groups", [])
    max_share = cfg.get("max_single_family_share", 0.35)
    notes: list[str] = []
    fam_scores: list[FamilyScore] = []
    supporting: list[Evidence] = []
    contradicting: list[Evidence] = []
    if direction not in (1, -1):
        raise ValueError("direction must be +1 or -1")

    by_family: dict[Family, list[Evidence]] = {}
    for e in items:
        if not e.available:
            continue
        by_family.setdefault(e.family, []).append(e)

    total_weight = 0.0
    weighted_sum = 0.0
    for fam in Family:
        w = weights.get(fam.value, 0.0)
        if w == 0.0:
            continue
        total_weight += w
        evs = by_family.get(fam, [])
        # collapse correlated groups: keep the strongest item per group
        used: list[Evidence] = []
        collapsed: list[Evidence] = []
        best_in_group: dict[str, Evidence] = {}
        for e in evs:
            g = e.correlated_group or _group_of(e.key, groups)
            if g is None:
                used.append(e)
                continue
            cur = best_in_group.get(g)
            if cur is None or e.strength > cur.strength:
                if cur is not None:
                    collapsed.append(cur)
                best_in_group[g] = e
            else:
                collapsed.append(e)
        used.extend(best_in_group.values())
        directional = [e for e in used if e.direction != 0]
        if directional:
            net = sum(e.direction * e.strength for e in directional) / len(directional)
        else:
            net = 0.0
        net = max(-1.0, min(1.0, net))
        contribution = w * net * direction
        weighted_sum += contribution
        fam_scores.append(FamilyScore(fam, w, net, used, collapsed, contribution))
        for e in used:
            if e.direction == 0:
                continue
            (supporting if e.direction == direction else contradicting).append(e)

    # weighted_sum is in [-total_weight, +total_weight]; map to 0..100
    score = 50.0 + 50.0 * (weighted_sum / total_weight if total_weight else 0.0)
    positive = [f for f in fam_scores if f.contribution > 0]
    independent = sum(1 for f in positive if f.net * direction >= 0.2)
    pos_total = sum(f.contribution for f in positive)
    dominant = max((f.contribution for f in positive), default=0.0) / pos_total if pos_total > 0 else 0.0
    if dominant > max_share and independent < cfg.get("min_independent_families_supporting", 3):
        notes.append(f"single family supplies {dominant:.0%} of positive score; capped by policy (max {max_share:.0%})")
        # cap: shrink the dominant family's excess contribution
        excess = (dominant - max_share) * pos_total
        score -= 50.0 * excess / total_weight if total_weight else 0.0
    return ScoreBreakdown(
        direction=direction,
        score=max(0.0, min(100.0, score)),
        threshold=float(cfg.get("research_threshold", 75)),
        families=fam_scores,
        supporting=sorted(supporting, key=lambda e: -e.strength),
        contradicting=sorted(contradicting, key=lambda e: -e.strength),
        independent_families_supporting=independent,
        dominant_family_share=dominant,
        config_version=cfg.get("version", "unknown"),
        notes=notes,
    )
