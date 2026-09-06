# 05 Responsible-finance assessment

**Purpose fit.** The application supports personal analysis and paper trading. It does not execute orders, custody funds or give personalised advice. Statuses are outputs of deterministic rules over public/licensed data.

**Truthfulness controls implemented.**
- No status is produced without data that passed integrity checks; missing data returns DATA UNAVAILABLE with the exact reason.
- Confidence is a calibrated frequency range with its sample size; when no validated sample exists the gate G17 blocks setups.
- Backtest, validation, paper and live samples are stored and displayed separately (`/performance`, `/api/performance/strategies`).
- Notification copy is checked against a banned-language list (guaranteed, risk-free, act now, …) and every setup carries the uncertainty statement.
- Pattern labels are limited to "Observed liquidity pattern", "Possible failed breakout", "Possible stop-run-like behaviour", "Confirmed strategy condition". The word manipulation does not appear in outputs.
- Slow public data (COT, ETF flows) is labelled with its report and publication dates and never called real-time flow.
- Demo data is impossible to mistake for live data: red banner, header, payload flag, provider notes.

**Conflicts and incentives.** The system has no revenue link to trade frequency. A high NO TRADE ratio is the expected outcome in most sessions (observed ~55% NO TRADE, ~44% WAIT, ~1% setups on synthetic data in `scratch` scans).

**Consumer protection gaps to close before any public use.** Jurisdiction-specific disclosures and terms (UAE SCA / other regulators), age and suitability checks, complaint handling, marketing rules, data-protection registration where required. These are placeholders in the welcome page and are listed in `36-production-readiness-assessment.md`.

**Harm minimisation.** Conservative default risk (0.5% per trade, 1.5% daily, 3% weekly, 6% monthly drawdown), server-enforced bounds, mandatory Friday review, weekend-gap warnings, explicit weekend-risk acknowledgement recorded in the audit log.
