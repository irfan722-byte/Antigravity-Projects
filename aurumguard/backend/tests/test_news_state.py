from datetime import UTC, datetime, timedelta, timezone

from app.core.news_state import EconomicEvent, Importance, NewsConfig, NewsPhase, Verification, assess_news_state

UTC = UTC
SCHED = datetime(2026, 3, 6, 13, 30, tzinfo=UTC)


def ev(**over):
    base = dict(event_id="e1", name="Nonfarm Payrolls", country="US", currency="USD", importance=Importance.HIGH, scheduled_ts=SCHED, source_tz="America/New_York", category="employment", provider="mock", ingested_ts=SCHED - timedelta(days=1), consensus=180.0, prior=170.0, higher_is_usd_positive=True, surprise_std=75.0, surprise_history_n=36)
    base.update(over)
    return EconomicEvent(**base)


def test_phases_progression():
    e = ev()
    assert assess_news_state([e], SCHED - timedelta(hours=3)).phase == NewsPhase.NONE
    s = assess_news_state([e], SCHED - timedelta(minutes=50))
    assert s.phase == NewsPhase.PRE_EVENT_WINDOW and s.scenarios and s.scenarios[0]["scenario"] == "STRONGER_THAN_CONSENSUS"
    assert assess_news_state([e], SCHED - timedelta(minutes=10)).phase == NewsPhase.PRE_EVENT_LOCKOUT
    # release passed, no actual yet
    s2 = assess_news_state([e], SCHED + timedelta(minutes=2))
    assert s2.phase == NewsPhase.RELEASE_LOCKOUT and s2.is_lockout
    # verified actual, inside cooldown
    e2 = ev(actual=250.0, published_ts=SCHED + timedelta(seconds=30), verification=Verification.VERIFIED)
    s3 = assess_news_state([e2], SCHED + timedelta(minutes=6))
    assert s3.phase == NewsPhase.POST_RELEASE_COOLDOWN and s3.reaction["standardised_surprise"] > 0.9
    # after cooldown, spread normal -> confirmation
    s4 = assess_news_state([e2], SCHED + timedelta(minutes=20), spread_now=0.3, median_spread=0.25, reaction_inputs={"dxy_response_sign": 1, "gold_response_sign": -1})
    assert s4.phase == NewsPhase.POST_RELEASE_CONFIRMATION and not s4.is_lockout
    assert s4.reaction["dxy_response_sign"] == 1
    # spread still wide keeps cooldown
    s5 = assess_news_state([e2], SCHED + timedelta(minutes=20), spread_now=0.9, median_spread=0.25)
    assert s5.phase == NewsPhase.POST_RELEASE_COOLDOWN
    # window expired
    assert assess_news_state([e2], SCHED + timedelta(hours=3)).phase == NewsPhase.NONE


def test_delayed_and_conflicting_release():
    e = ev()
    s = assess_news_state([e], SCHED + timedelta(minutes=40))
    assert s.phase == NewsPhase.RELEASE_LOCKOUT and any("delayed" in r for r in s.reasons)
    c = ev(actual=1.0, verification=Verification.CONFLICT, published_ts=SCHED)
    s2 = assess_news_state([c], SCHED + timedelta(minutes=30))
    assert s2.phase == NewsPhase.RELEASE_LOCKOUT and any("disagree" in r for r in s2.reasons)


def test_low_importance_and_non_usd_ignored():
    low = ev(importance=Importance.LOW)
    assert assess_news_state([low], SCHED - timedelta(minutes=5)).phase == NewsPhase.NONE
    eur = ev(currency="EUR")
    assert assess_news_state([eur], SCHED - timedelta(minutes=5)).phase == NewsPhase.NONE


def test_standardised_surprise_requires_history():
    e = ev(actual=250.0, surprise_history_n=5)
    assert e.surprise == 70.0 and e.standardised_surprise is None
    e2 = ev(actual=250.0)
    assert abs(e2.standardised_surprise - 70 / 75) < 1e-9


def test_revision_flag_in_reaction():
    e = ev(actual=200.0, revised_prior=160.0, published_ts=SCHED, verification=Verification.VERIFIED)
    s = assess_news_state([e], SCHED + timedelta(minutes=20), spread_now=0.3, median_spread=0.3)
    assert s.reaction["revision_flag"] is True
