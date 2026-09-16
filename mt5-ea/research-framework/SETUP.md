# Step-by-step: run the mt5-research-framework and generate the EA

Follow in order. Every step is required. This is **Windows only** (the framework
drives MetaTrader 5 through the Windows CLI).

> Two facts to keep in mind so nothing surprises you:
> - The framework **generates** the `.mq5`/`.ex5` when you run it. There is no
>   pre-made EA file to copy.
> - The generated EA `#include`s the **MyLibs** library (`mt5-quant-lib`). If
>   that isn't installed correctly, compilation fails. Step 4 handles it.

---

## 0. Prerequisites (install once)

1. **MetaTrader 5** — installed from your broker, logged into your account.
2. **Python 3.8+** — during install tick **"Add Python to PATH"**.
3. **Git for Windows** — https://git-scm.com/download/win

Check in a Command Prompt:
```bat
python --version
git --version
```
Both must print a version. If `python` isn't found, reinstall Python with the
PATH option ticked.

---

## 1. Find your MT5 "data folder" (Terminal ID)

1. Open MT5 → **File → Open Data Folder**. Explorer opens at something like:
   ```
   C:\Users\<You>\AppData\Roaming\MetaQuotes\Terminal\1A2B3C4D5E6F...\
   ```
2. That long folder name `1A2B3C4D5E6F...` is your **Terminal ID**. Copy the
   **full path** — you need it several times below. Inside it you'll see an
   `MQL5` folder with `Experts` and `Include` subfolders.

---

## 2. Clone the framework INTO the Experts folder

In Command Prompt (paste your real path):
```bat
cd "C:\Users\<You>\AppData\Roaming\MetaQuotes\Terminal\<Terminal_ID>\MQL5\Experts"
git clone https://github.com/xMattC/mt5-research-framework.git
cd mt5-research-framework
```
> The repo's own README calls itself `mt5-strategy-factory` (an older name). Use
> the URL above — it's the repo you gave me. If that clone 404s, try
> `git clone https://github.com/xMattC/mt5-strategy-factory.git` instead; the
> contents are the same.

---

## 3. Python virtual environment + dependencies

Still inside the `mt5-research-framework` folder:
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
Your prompt should now start with `(.venv)`. If `activate` is blocked, run
PowerShell as admin once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

---

## 4. Install the MyLibs library (this is the step people miss)

The generated EAs do `#include <MyLibs/...>`, so the library folder **must be
named exactly `MyLibs`** and live in the `Include` folder:
```bat
cd "C:\Users\<You>\AppData\Roaming\MetaQuotes\Terminal\<Terminal_ID>\MQL5\Include"
git clone https://github.com/xMattC/mt5-quant-lib.git MyLibs
```
Verify the path exists afterwards:
```
...\MQL5\Include\MyLibs\BacktestUtils\CustomMax.mqh
```
If that file isn't there, the name/location is wrong and every compile will fail.

---

## 5. Tell the framework where MT5 is

Edit `mt5-research-framework\config\local_paths.yaml` with **your real paths**:
```yaml
mt5_root: "C:/Users/<You>/AppData/Roaming/MetaQuotes/Terminal/<Terminal_ID>"
mt5_terminal_exe: "C:/Program Files/<YourBroker> MetaTrader 5/terminal64.exe"
mt5_meta_editor_exe: "C:/Program Files/<YourBroker> MetaTrader 5/metaeditor64.exe"
strategy_factory_root: "C:/Users/<You>/AppData/Roaming/MetaQuotes/Terminal/<Terminal_ID>/MQL5/Experts/mt5-research-framework"
```
Notes:
- Use **forward slashes** `/` as shown.
- `terminal64.exe` / `metaeditor64.exe` are in your broker's MT5 install folder
  (right-click the MT5 desktop icon → Open file location if unsure).

---

## 6. Add the indicators I wrote

Copy the three YAMLs from `mt5-ea/research-framework/indicators/...` (in your
Antigravity-Projects repo) into the framework's matching folders:
```
mt5-research-framework\indicators\trend_following\trigger_conf_exit\bollinger.yaml
mt5-research-framework\indicators\trend_following\trendline\ichimoku.yaml
mt5-research-framework\indicators\trend_following\trendline\dema.yaml
```
They sit next to the shipped rsi/macd/adx/ema/... files. (Optional — the
framework already ships enough indicators to run without these.)

---

## 7. Prepare the market data in MT5

1. In MT5 **Market Watch**, right-click → **Symbols**, find your gold symbol
   (yours is **`XAUUSDm`**) and enable it so it shows in Market Watch.
2. Open a `XAUUSDm` chart, set it to **H1**, and scroll back a few years so MT5
   downloads history (Tools → Options → Charts → "Max bars" high helps).
   No history = empty optimisation results.

---

## 8. Create the project and drop in the config

From the framework folder with `(.venv)` active:
```bat
python main.py
```
This scaffolds a new project folder (it prints the name, e.g. `Apollo/`) with
`config.yaml`, `whitelist.yaml`, `run.py` inside.

Now replace those two files with mine (from `mt5-ea/research-framework/`):
- copy my **`config.yaml`** over the generated one,
- copy my **`whitelist.yaml`** over the generated one.

**Open `whitelist.yaml` and confirm the symbol is exactly `XAUUSDm`** (whatever
Market Watch shows). Wrong symbol = zero trades.

---

## 9. Run the pipeline, stage by stage

```bat
python run.py
```
It runs the **Trigger** stage first: generates EAs, compiles them, runs MT5
optimisation, writes results to
`Outputs\xauusd_trend\Trigger\results\` (`best_summary.csv`, `scored_results.csv`).

Then it **pauses**. You pick the winning indicator and create the handoff file,
e.g. if RSI won the Trigger stage:
```bat
python -m strategy_factory.post_processing.make_stage_result_file --indicator RSI --stage Trigger
```
Re-run `python run.py`; it moves to **Conformation**, then repeat the
review-and-select step for each stage in order:

```
Trigger -> Conformation -> Trendline -> Volume -> Exit
```

Indicator names to pass with `--indicator` are the ones from that stage's results
(e.g. `RSI`, `MACD`, `ADX`, `BOLLINGER`, `EMA`, `DEMA`, `ICHIMOKU`, `MFI`, `OBV`).
After the **Exit** stage is selected, the framework assembles the final EA.

---

## 10. Where the generated EA ends up

Compiled EAs and configs for each stage are under:
```
mt5-research-framework\Outputs\xauusd_trend\<Stage>\experts\   <- the .mq5 and .ex5
mt5-research-framework\Outputs\xauusd_trend\<Stage>\results\   <- scores
mt5-research-framework\Outputs\xauusd_trend\<Stage>\logs\      <- read these on any failure
```
The `.ex5` there is loadable in MT5 like any EA (it still needs MyLibs present).

---

## Troubleshooting (most common failures)

| Symptom | Fix |
|--------|-----|
| Compile fails, "cannot open include file MyLibs/..." | Step 4 wrong — folder must be `...\MQL5\Include\MyLibs\...` (exact name). |
| MT5 doesn't launch / no results | `local_paths.yaml` paths wrong; check `terminal64.exe` path. |
| Empty results / zero trades | Symbol name in `whitelist.yaml` ≠ Market Watch symbol; or no price history downloaded (Step 7). |
| `python` not found | Reinstall Python with "Add to PATH". |
| `activate` blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` in PowerShell. |
| Anything else | Open the newest file in `Outputs\...\logs\` — it names the real error. |

---

## Honest expectations

- This is a **research/optimisation** tool, not a push-button money machine. It
  produces a directional trend-following EA whose quality depends entirely on the
  out-of-sample numbers you see at each stage. Judge by OOS, not in-sample.
- The framework is a personal/portfolio project ("limited test coverage",
  "manual selection", "Windows-focused") — expect a few rough edges. When a step
  errors, the `logs/` folder is the source of truth.
- If you just want a single EA file that runs today with no Python and no extra
  library, that's the standalone `IronwallHedge.mq5` in the folder above — this
  framework is a different, heavier path.
