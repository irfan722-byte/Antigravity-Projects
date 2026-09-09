# 17 Backtesting methodology

Engine: `backtest/engine.py` replays the same strategy, structure, regime, risk and paper-execution code as live.

Protections: candle slices cut at `t` (no future bars); forming bar discarded; calendar events viewed as of `t` (actuals stripped before release + 20 s); fills at the next M1 open at bid/ask plus slippage; stops/targets on M1 bars; conservative same-bar rule (stop first, labelled `CONSERVATIVE_SAME_BAR`); gap-through-stop fills at the open with extra slippage (labelled); spread from the candle; session/weekend logic shared with live; Friday closure for swing/weekly; positions still open at the end closed and labelled `END_OF_TEST`; deterministic ids; config hash and trades hash for reproducibility (tested).

Validation (`backtest/validation.py`): rolling walk-forward with a 2-day embargo; in-sample and out-of-sample metrics kept separate; threshold sensitivity on the OOS set only; Monte Carlo reshuffle of trade order (drawdown p50/p95/p99, probability of loss, stated i.i.d. assumption); cost sensitivity at 0.5×, 1×, 1.5×, 2× spread+slippage; parameter stability helper; buy-and-hold benchmark; multiple-testing caution (Bonferroni-style family-wise risk from the number of configurations examined); calibration payload (OOS buckets) and acceptance checklist for a human.

Metrics (`backtest/metrics.py`): trades, win/loss rate with Wilson CI, average win/loss (USD and R), expectancy with bootstrap CI, profit factor, net and gross before costs, cost share, max/average drawdown, recovery length, streaks, exposure, long/short, by year/month/session/regime/event proximity/exit reason, labelled fills, Sharpe- and Sortino-like per-trade figures with an explicit limitation note, return-to-drawdown, calibration buckets and Brier.

Limits: candle-based fills are insufficient for scalp modelling (stated in every result); the demo path is synthetic; five years of licensed history is a target, not a claim.
