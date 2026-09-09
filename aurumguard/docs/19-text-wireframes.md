# 19 Text wireframes (mobile-first)

```
[DEMO DATA banner - red, full width]
[☰] AurumGuard          XAU/USD 2,412.30 / 2,412.55  spr 0.25 · LONDON_NY_OVERLAP  [theme][Log out]

DASHBOARD
┌ Bid/Ask ┐ ┌ Market/session ┐ ┌ Next USD event: 3h 20m ┐ ┌ Regime: STRONG_TREND 71% ┐
Decisions by horizon
┌ SCALP  ■ NO TRADE  …reason… [Setup details] [Evidence Inspector] ┐
┌ INTRADAY ▲ BUY SETUP  entry 2,410.1–2,411.3 · stop 2,404.9 · TP1 2,418.0 (R 1.7) · TP2 2,425.5 (R 2.9) · expires 16:00 GST · 0.08 lots · 46.2 USD · conf 48–66% (n=61) ┐
┌ SWING  ◔ WAIT … ┐ ┌ WEEKLY ■ NO TRADE (no new weekly setups within 4h of Friday cutoff) ┐
Risk: equity · aggregate risk · today · week · open positions · locks
Data health: all providers healthy · mock providers active (DEMO)
Latest actionable and recent setups · Strategy performance summary (OOS vs paper)
[bottom nav: Dashboard | Signals | Charts | Paper | Notifications]

SETUP DETAILS  (39 mandatory rows in a table) → [Take in paper account] [Evidence Inspector]
EVIDENCE INSPECTOR (21 numbered sections; outcome section empty until expiry)
CALENDAR (table: local time, countdown, event, importance, actual, consensus, prior, revised prior, surprise z, verified)
EVENT DETAIL (values · scenario table with sample sizes · verified reaction JSON · config)
PAPER (KPIs realised/unrealised/open risk · open table with Close · pending/rejected · closed)
SETTINGS (risk limits with bounds · Friday cutoff · event preference · quiet hours · auto paper · weekend override · MFA)
NOTIFICATION CENTRE (push status + enable button · history with delivery status)
```
