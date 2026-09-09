# 18 Product information architecture

Groups and pages (all implemented under `frontend/src/app`):
- Trade: Dashboard, Signal feed, Charts, Paper trading, Trade journal, Setup details (`/setups/[id]`), Evidence Inspector (`/evidence/[id]`)
- Context: Economic calendar, Event detail (`/calendar/[id]`), Market regime, Intermarket
- Risk: Risk dashboard, Position-size calculator
- Research: Strategy registry, Backtesting laboratory, Performance, Probability calibration
- System: Notification centre, Data-provider health, Settings, Privacy controls, Audit dashboard, Administration (admin only)
- Entry: Welcome and disclosure, Register, Login, Onboarding

Dashboard priorities implemented: bid/ask/spread, market state and session, next major USD event with countdown, regime, four horizon decisions, active paper positions and aggregate risk, daily and weekly result, risk-lock status, data-health status, latest actionable and recent setups, strategy performance summary.

Mobile: bottom navigation (Dashboard, Signals, Charts, Paper, Notifications), collapsible side navigation, tables scroll horizontally, cards stack.
