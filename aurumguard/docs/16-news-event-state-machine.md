# 16 News-event state machine

Config (`NewsConfig`): notify 60 min before, lockout 30 min before, minimum 5 min release lockout, 10 min cooldown, 120 min confirmation window, 30 min max release delay, spread must be ≤ 1.5× median to leave cooldown, minimum importance HIGH, USD only.

Phases: NONE → PRE_EVENT_WINDOW (scenario table: stronger/weaker/mixed with historical reaction stats and sample sizes, or "unavailable") → PRE_EVENT_LOCKOUT → RELEASE_LOCKOUT (until actual is VERIFIED; CONFLICT between providers or delay > 30 min keeps the lockout and says why) → POST_RELEASE_COOLDOWN (spread monitored) → POST_RELEASE_CONFIRMATION (reaction object: actual, consensus, prior, revised prior + revision flag, surprise, standardised surprise when ≥ 12 historical surprises, DXY/10y/gold response signs, conflicting components) → NONE.

Only strategies that declare NEWS_DOMINATED as an approved regime (PNC-M15, research status) evaluate in the confirmation phase; all others treat PRE_EVENT_WINDOW as contradictory evidence and the lockout phases as G06 failures. "Actual beat consensus" never produces a direction on its own: PNC requires DXY, gold and M15 structure to agree.
