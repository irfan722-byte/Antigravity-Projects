# XAUUSD trend-following run — for xMattC/mt5-research-framework

This folder holds the inputs to build an EA with the
[mt5-research-framework](https://github.com/xMattC/mt5-research-framework).

**Read this first — what the framework does and doesn't do:**

- It is a **Python research pipeline**, not a hand-written EA. You give it a
  library of indicator definitions; it generates MQL5, optimises each of five
  stages (Trigger → Confirmation → Trendline → Volume → Exit) in the MT5
  Strategy Tester, and you pick the winner at each stage. The final EA is
  **produced on your machine when you run the pipeline** — it needs
  **Windows + a local MetaTrader 5 + the "MT5 Quant Lib"** the framework
  depends on. It cannot be produced in this cloud session.
- The strategy it builds is **directional and single-position** (one trade at a
  time, indicator entry, risk-based SL/TP). It has nothing to do with the
  IRONWALL HEDGE martingale EA in `../` — that one does not fit this framework.

## What's in here

| File | What it is |
|------|------------|
| `config.yaml` | The run config: XAUUSD, H1, dates, account, per-stage optimiser settings. |
| `whitelist.yaml` | Instrument list — **set the exact broker symbol** (your MT5 shows `XAUUSDm`). |
| `indicators/trend_following/trigger_conf_exit/bollinger.yaml` | New Trigger/Confirmation/Exit indicator: Bollinger band breakout (`iBands`). |
| `indicators/trend_following/trendline/ichimoku.yaml` | New Trendline: Ichimoku Kijun-sen (`iIchimoku`). |
| `indicators/trend_following/trendline/dema.yaml` | New Trendline: DEMA (`iMA` MODE_DEMA). |

All three indicator files use **built-in MT5 functions only** (`custom: false`),
so they need no extra custom indicators installed. They follow the framework's
exact schema (checked against the shipped `rsi.yaml`, `ema.yaml`, `mfi.yaml`).

## How to use it

1. Clone the framework and install deps (Windows, with MT5 installed):
   ```bash
   git clone https://github.com/xMattC/mt5-research-framework
   cd mt5-research-framework
   pip install -r requirements.txt
   ```
   Also install its **MT5 Quant Lib** dependency into your MT5 `Include/`
   folder (see the framework README) and set paths in `config/local_paths.yaml`.

2. Add the new indicators: copy the files under this folder's
   `indicators/trend_following/...` into the framework's own
   `indicators/trend_following/...` tree (same sub-paths). They sit alongside
   the shipped rsi/macd/adx/… so the optimiser includes them.

3. Scaffold a project and drop in the config:
   ```bash
   python main.py            # creates a project folder with config.yaml, whitelist.yaml, run.py
   ```
   Replace the generated `config.yaml` and `whitelist.yaml` with the ones here
   (or copy the values across). **Edit `whitelist.yaml` so the symbol matches
   your broker exactly** — `XAUUSDm`, `XAUUSD`, `GOLD`, etc. A wrong symbol =
   zero trades and empty results.

4. Run the pipeline and select a winner after each stage:
   ```bash
   python run.py
   ```
   After each stage, review `Outputs/xauusd_trend/<Stage>/results/` and pick the
   indicator to keep:
   ```bash
   python -m strategy_factory.post_processing.make_stage_result_file --indicator BOLLINGER --stage Trigger
   ```
   Repeat for Conformation, Trendline, Volume, Exit. The final stage assembles
   the complete EA.

## Honest notes

- **H1, not M1.** Your screenshots were M1. M1 trend-following on gold is mostly
  noise and will overfit badly in an optimiser. I set `period: H1`. Change it in
  `config.yaml` if you truly want M1 — but expect worse out-of-sample results.
- **This does not inherit any edge.** The framework's value is disciplined
  IS/OOS testing and stage-gating, which reduces overfitting — it does not
  guarantee a profitable system. Judge each stage by its out-of-sample numbers.
- I could not run the pipeline here (needs Windows + MT5). These are validated
  against the framework's schema, but compile/run them locally before trusting.
