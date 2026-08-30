//+------------------------------------------------------------------+
//|                                      FairValueRange_XAUUSD.mq4    |
//|                Patrick Nil "Fair Value Range" Strategy for Gold   |
//|                        Optimized for XAUUSD on the M15 timeframe  |
//+------------------------------------------------------------------+
#property copyright "Fair Value Range EA"
#property link      ""
#property version   "1.00"
#property strict
#property description "Fair Value Range strategy for XAUUSD (Gold) on M15."
#property description "Impulse + lateral range detection, range & breakout trading,"
#property description "aggressive 5% risk sizing, 1:3 R:R enforcement, SL lockdown,"
#property description "and daily circuit breakers."

//+------------------------------------------------------------------+
//| Input parameters                                                 |
//+------------------------------------------------------------------+
input string  Sec_General          = "======= General =======";
input int     MagicNumber          = 20260830;   // Unique magic number for this EA
input string  TradeComment         = "FVR_XAUUSD";
input bool    EnableRangeTrading    = true;        // Trade rejections inside the range
input bool    EnableBreakoutTrading = true;        // Trade validated breakouts

input string  Sec_Impulse          = "======= Impulse / Range =======";
input int     ATR_Period           = 14;          // ATR period for impulse detection
input double  ImpulseATRmult       = 1.8;         // Candle range >= mult * ATR = impulse
input int     ImpulseMaxCandles     = 3;           // Impulse spans 1..N candles
input int     RangeScanBars        = 120;         // Bars to scan when mapping the box
input int     FractalTouchesReq     = 3;           // Min. distinct fractal touches per side
input double  TouchTolerancePts     = 40;          // Tolerance (points) to count a boundary touch
input int     MinRangeBars         = 6;           // Min. bars a valid range must span

input string  Sec_Trade            = "======= Trade Execution =======";
input double  PendingBufferPts      = 15;          // Buffer (points) beyond fractal for stop orders
input double  MinRR                = 3.0;         // Minimum Risk:Reward ratio (1:3)
input int     PendingExpiryBars     = 12;          // Bars until a pending order expires (0 = GTC)

input string  Sec_Risk             = "======= Risk / Money Mgmt =======";
input double  RiskPercent          = 5.0;         // Risk per trade (% of equity)
input double  DailyLossPercent      = 15.0;        // Daily equity drawdown circuit breaker (%)
input int     MaxConsecLosses       = 3;           // Consecutive losses that suspend trading

input string  Sec_Safeguards       = "======= XAUUSD Safeguards =======";
input double  MaxSpreadPoints       = 30;          // Max allowed spread (points)
input int     SlippagePoints        = 20;          // Max slippage buffer (points)

//+------------------------------------------------------------------+
//| Globals                                                          |
//+------------------------------------------------------------------+
double   g_pip;                 // one "point" in price terms (Point)
double   g_pointsPerPrice;      // 1.0 / Point (points contained in a price unit)
datetime g_lastBarTime  = 0;    // last processed M15 bar time
datetime g_suspendUntil = 0;    // trading suspended until this time (broker midnight)
double   g_dayStartEquity = 0;  // equity snapshot at start of broker day
int      g_dayStamp     = -1;   // Day() we captured the equity snapshot for

// Validated range boundaries
bool     g_rangeValid   = false;
double   g_rangeUpper   = 0.0;
double   g_rangeLower   = 0.0;
double   g_impulsePts   = 0.0;  // magnitude of the impulse move (points) for projection

// Breakout state machine
enum ENUM_BO_STATE
  {
   BO_IDLE      = 0,   // waiting for a close outside the range
   BO_CLOSED_UP = 1,   // closed above upper, awaiting retrace + fractal
   BO_CLOSED_DN = 2    // closed below lower, awaiting retrace + fractal
  };
ENUM_BO_STATE g_boState   = BO_IDLE;
bool          g_boRetraced = false;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
  {
   // Broker formatting: derive point size dynamically so the EA works on
   // 2-digit and 3-digit Gold feeds alike.
   g_pip = Point;
   if(g_pip <= 0.0)
      g_pip = MathPow(10, -Digits);
   g_pointsPerPrice = 1.0 / g_pip;

   if(RiskPercent <= 0.0 || RiskPercent > 100.0)
     {
      Print("FVR: invalid RiskPercent, must be in (0,100].");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(MinRR <= 0.0)
     {
      Print("FVR: invalid MinRR.");
      return(INIT_PARAMETERS_INCORRECT);
     }

   CaptureDayStart(true);

   PrintFormat("FVR init on %s Digits=%d Point=%.5f | Risk=%.1f%% MinRR=1:%.1f",
               Symbol(), Digits, Point, RiskPercent, MinRR);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
  }

//+------------------------------------------------------------------+
//| Main tick handler                                                |
//+------------------------------------------------------------------+
void OnTick()
  {
   // Refresh the daily equity anchor at each new broker day.
   CaptureDayStart(false);

   // Enforce break-even-only SL discipline on every tick (fast path).
   EnforceStopLossLockdown();

   // Circuit breakers gate everything below.
   if(!TradingAllowed())
      return;

   // Only run the heavy structural logic once per closed M15 bar.
   if(!IsNewBar())
      return;

   // Volatility guard: skip when spread is too wide for the 5% risk model.
   if(CurrentSpreadPoints() > MaxSpreadPoints)
      return;

   // 1) Detect impulse + validate the lateral consolidation box.
   UpdateRange();

   if(!g_rangeValid)
     {
      g_boState = BO_IDLE;
      g_boRetraced = false;
      return;
     }

   // 2) Trade logic.
   if(EnableRangeTrading)
      ManageRangeOrders();

   if(EnableBreakoutTrading)
      ManageBreakoutStateMachine();
  }

//+------------------------------------------------------------------+
//| New-bar detector (M15)                                           |
//+------------------------------------------------------------------+
bool IsNewBar()
  {
   datetime t = Time[0];
   if(t != g_lastBarTime)
     {
      g_lastBarTime = t;
      return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| Current spread in points                                         |
//+------------------------------------------------------------------+
double CurrentSpreadPoints()
  {
   return((Ask - Bid) * g_pointsPerPrice);
  }

//+------------------------------------------------------------------+
//| Broker-midnight helper: start of the current broker day          |
//+------------------------------------------------------------------+
datetime BrokerDayStart()
  {
   datetime now = TimeCurrent();
   return(now - (now % 86400));
  }

datetime NextBrokerMidnight()
  {
   return(BrokerDayStart() + 86400);
  }

//+------------------------------------------------------------------+
//| Capture the equity anchor at the start of each broker day        |
//+------------------------------------------------------------------+
void CaptureDayStart(bool force)
  {
   int d = Day();
   if(force || d != g_dayStamp)
     {
      g_dayStamp        = d;
      g_dayStartEquity  = AccountEquity();
     }
  }

//+------------------------------------------------------------------+
//| Circuit breakers: consecutive losses & daily drawdown            |
//+------------------------------------------------------------------+
bool TradingAllowed()
  {
   // Hard suspension window (until broker midnight).
   if(g_suspendUntil > 0)
     {
      if(TimeCurrent() < g_suspendUntil)
         return(false);
      g_suspendUntil = 0;   // window elapsed
     }

   // Daily realized+floating equity drawdown breaker.
   if(g_dayStartEquity > 0.0)
     {
      double dd = (g_dayStartEquity - AccountEquity()) / g_dayStartEquity * 100.0;
      if(dd >= DailyLossPercent)
        {
         SuspendUntilMidnight("daily drawdown limit hit");
         return(false);
        }
     }

   // Consecutive-loss breaker (today's closed trades for this magic).
   if(ConsecutiveLossesToday() >= MaxConsecLosses)
     {
      SuspendUntilMidnight("consecutive loss limit hit");
      return(false);
     }

   return(true);
  }

void SuspendUntilMidnight(string why)
  {
   if(g_suspendUntil == 0)
      PrintFormat("FVR: trading suspended until broker midnight (%s).", why);
   g_suspendUntil = NextBrokerMidnight();
  }

//+------------------------------------------------------------------+
//| Count consecutive closing losses for today's history            |
//+------------------------------------------------------------------+
int ConsecutiveLossesToday()
  {
   datetime dayStart = BrokerDayStart();
   int total = OrdersHistoryTotal();

   // Walk history newest-first; MT4 history is not strictly ordered, so we
   // collect today's closed deals, then evaluate them by close time.
   datetime bestTimes[];
   double   bestProfits[];
   int      n = 0;
   ArrayResize(bestTimes, total);
   ArrayResize(bestProfits, total);

   for(int i = 0; i < total; i++)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY))
         continue;
      if(OrderMagicNumber() != MagicNumber)
         continue;
      if(OrderSymbol() != Symbol())
         continue;
      int t = OrderType();
      if(t != OP_BUY && t != OP_SELL)   // only real closed positions
         continue;
      if(OrderCloseTime() < dayStart)
         continue;

      bestTimes[n]   = OrderCloseTime();
      // Net result of the trade including costs.
      bestProfits[n] = OrderProfit() + OrderSwap() + OrderCommission();
      n++;
     }

   if(n == 0)
      return(0);

   // Sort by close time ascending (simple insertion sort, n is small).
   for(int a = 1; a < n; a++)
     {
      datetime kt = bestTimes[a];
      double   kp = bestProfits[a];
      int b = a - 1;
      while(b >= 0 && bestTimes[b] > kt)
        {
         bestTimes[b + 1]   = bestTimes[b];
         bestProfits[b + 1] = bestProfits[b];
         b--;
        }
      bestTimes[b + 1]   = kt;
      bestProfits[b + 1] = kp;
     }

   // Count the trailing run of losses.
   int streak = 0;
   for(int k = n - 1; k >= 0; k--)
     {
      if(bestProfits[k] < 0.0)
         streak++;
      else
         break;
     }
   return(streak);
  }

//+------------------------------------------------------------------+
//| Fractal helpers (standard 5-bar swing on M15)                    |
//+------------------------------------------------------------------+
// A swing high forms at index i if High[i] is the highest of the surrounding
// 2 bars on each side. Symmetric for swing lows.
bool IsFractalHigh(int i)
  {
   if(i < 2 || i > Bars - 3)
      return(false);
   double h = High[i];
   return(h > High[i-1] && h > High[i-2] && h > High[i+1] && h > High[i+2]);
  }

bool IsFractalLow(int i)
  {
   if(i < 2 || i > Bars - 3)
      return(false);
   double l = Low[i];
   return(l < Low[i-1] && l < Low[i-2] && l < Low[i+1] && l < Low[i+2]);
  }

//+------------------------------------------------------------------+
//| Impulse detection: 14-ATR expansion over 1..N candles            |
//| Returns true and fills startIdx/impulsePts when an impulse ends  |
//| just before the consolidation we are mapping.                    |
//+------------------------------------------------------------------+
bool DetectImpulse(int searchFrom, int &impulseEndIdx, double &impulsePts)
  {
   double atr = iATR(NULL, PERIOD_M15, ATR_Period, searchFrom + ImpulseMaxCandles + 1);
   if(atr <= 0.0)
      return(false);

   // Look for a run of 1..ImpulseMaxCandles whose net displacement exceeds
   // ImpulseATRmult * ATR -> a "P" or "B" impulse formation.
   for(int start = searchFrom; start < searchFrom + RangeScanBars && start + ImpulseMaxCandles + 1 < Bars; start++)
     {
      for(int span = 1; span <= ImpulseMaxCandles; span++)
        {
         int hi = start + span;                 // older end of the leg
         int lo = start;                        // newer end of the leg
         double disp = MathAbs(Close[lo] - Close[hi + 1]);
         if(disp >= ImpulseATRmult * atr)
           {
            impulseEndIdx = lo;                  // impulse resolves here
            impulsePts    = disp * g_pointsPerPrice;
            return(true);
           }
        }
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| Update / validate the lateral consolidation box                  |
//+------------------------------------------------------------------+
void UpdateRange()
  {
   g_rangeValid = false;

   int impulseEnd = -1;
   double impPts  = 0.0;
   // The consolidation forms AFTER the impulse, i.e. on more recent bars,
   // so we search for an impulse that concluded within the scan window.
   if(!DetectImpulse(1, impulseEnd, impPts))
      return;

   // Map the box on the bars newer than the impulse end (1..impulseEnd).
   int boxFrom = 1;
   int boxTo   = MathMin(impulseEnd, RangeScanBars);
   if(boxTo - boxFrom + 1 < MinRangeBars)
      return;

   double hi = -DBL_MAX;
   double lo =  DBL_MAX;
   for(int i = boxFrom; i <= boxTo; i++)
     {
      if(High[i] > hi) hi = High[i];
      if(Low[i]  < lo) lo = Low[i];
     }
   if(hi <= lo)
      return;

   double tol = TouchTolerancePts * g_pip;

   // Require at least FractalTouchesReq distinct fractal swing highs near the
   // upper boundary and swing lows near the lower boundary.
   int upperTouches = 0;
   int lowerTouches = 0;
   for(int i = boxFrom; i <= boxTo; i++)
     {
      if(IsFractalHigh(i) && MathAbs(High[i] - hi) <= tol)
         upperTouches++;
      if(IsFractalLow(i) && MathAbs(Low[i] - lo) <= tol)
         lowerTouches++;
     }

   if(upperTouches < FractalTouchesReq || lowerTouches < FractalTouchesReq)
      return;

   // Range validated.
   g_rangeValid = true;
   g_rangeUpper = hi;
   g_rangeLower = lo;
   g_impulsePts = impPts;
  }

//+------------------------------------------------------------------+
//| Find the nearest historical consolidation zone for targeting     |
//| Direction: +1 look above entry, -1 look below entry.             |
//| Returns the target price, or 0.0 if none found.                  |
//+------------------------------------------------------------------+
double NearestHistoricalZone(double fromPrice, int direction)
  {
   double best = 0.0;
   double bestDist = DBL_MAX;
   double tol = TouchTolerancePts * g_pip;

   // Group fractals by price level; a level touched multiple times is a zone.
   for(int i = 3; i < RangeScanBars * 2 && i < Bars - 3; i++)
     {
      double level = 0.0;
      bool ok = false;
      if(direction > 0 && IsFractalHigh(i) && High[i] > fromPrice + tol)
        { level = High[i]; ok = true; }
      if(direction < 0 && IsFractalLow(i) && Low[i] < fromPrice - tol)
        { level = Low[i]; ok = true; }
      if(!ok)
         continue;

      // Count corroborating touches near this level.
      int touches = 0;
      for(int j = 3; j < RangeScanBars * 2 && j < Bars - 3; j++)
        {
         if(direction > 0 && IsFractalHigh(j) && MathAbs(High[j] - level) <= tol) touches++;
         if(direction < 0 && IsFractalLow(j)  && MathAbs(Low[j]  - level) <= tol) touches++;
        }
      if(touches < 2)
         continue;

      double dist = MathAbs(level - fromPrice);
      if(dist < bestDist)
        {
         bestDist = dist;
         best     = level;
        }
     }
   return(best);
  }

//+------------------------------------------------------------------+
//| Compute a Take Profit target for a trade                         |
//| entry, direction (+1 buy / -1 sell). Returns TP price or 0.      |
//+------------------------------------------------------------------+
double ComputeTakeProfit(double entry, int direction)
  {
   double zone = NearestHistoricalZone(entry, direction);
   if(zone > 0.0)
      return(zone);

   // No structural zone above/below (e.g. all-time high): project the
   // measured impulse distance outward from the entry.
   double proj = g_impulsePts * g_pip;
   if(proj <= 0.0)
      return(0.0);
   if(direction > 0)
      return(entry + proj);
   else
      return(entry - proj);
  }

//+------------------------------------------------------------------+
//| Lot sizing: risk exactly RiskPercent of equity over SL distance  |
//+------------------------------------------------------------------+
double CalculateLotSize(double slDistancePrice, int cmd, double price)
  {
   if(slDistancePrice <= 0.0)
      return(0.0);

   double equity     = AccountEquity();
   double riskMoney  = equity * (RiskPercent / 100.0);

   double tickValue  = MarketInfo(Symbol(), MODE_TICKVALUE); // money per tick per lot
   double tickSize   = MarketInfo(Symbol(), MODE_TICKSIZE);
   if(tickSize <= 0.0)
      tickSize = Point;
   if(tickValue <= 0.0)
      return(0.0);

   // Loss per 1.0 lot if SL is hit.
   double lossPerLot = (slDistancePrice / tickSize) * tickValue;
   if(lossPerLot <= 0.0)
      return(0.0);

   double lots = riskMoney / lossPerLot;

   // Normalize strictly to the broker's lot step and min/max bounds.
   double lotStep = MarketInfo(Symbol(), MODE_LOTSTEP);
   double minLot  = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot  = MarketInfo(Symbol(), MODE_MAXLOT);
   if(lotStep <= 0.0) lotStep = 0.01;

   lots = MathFloor(lots / lotStep) * lotStep;   // round DOWN so we never exceed 5%
   if(lots < minLot)
      lots = 0.0;                                // too small to place safely
   if(lots > maxLot)
      lots = maxLot;

   lots = NormalizeDouble(lots, 2);
   if(lots <= 0.0)
      return(0.0);

   // Margin guard: ensure the generated size will not be rejected.
   double freeCheck = AccountFreeMarginCheck(Symbol(), cmd, lots);
   if(freeCheck <= 0.0 || GetLastError() == 134 /*ERR_NOT_ENOUGH_MONEY*/)
     {
      // Step the size down until margin is sufficient.
      while(lots >= minLot)
        {
         lots = NormalizeDouble(lots - lotStep, 2);
         if(lots < minLot)
            return(0.0);
         if(AccountFreeMarginCheck(Symbol(), cmd, lots) > 0.0)
            break;
        }
     }
   if(lots < minLot)
      return(0.0);
   return(lots);
  }

//+------------------------------------------------------------------+
//| R:R enforcer                                                     |
//+------------------------------------------------------------------+
bool PassesRR(double entry, double sl, double tp)
  {
   double risk   = MathAbs(entry - sl);
   double reward = MathAbs(tp - entry);
   if(risk <= 0.0 || reward <= 0.0)
      return(false);
   return((reward / risk) >= MinRR);
  }

//+------------------------------------------------------------------+
//| Count live orders (open + pending) for this EA on this symbol    |
//+------------------------------------------------------------------+
int CountMyOrders(int typeFilter = -1)
  {
   int c = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderMagicNumber() != MagicNumber || OrderSymbol() != Symbol())
         continue;
      if(typeFilter >= 0 && OrderType() != typeFilter)
         continue;
      c++;
     }
   return(c);
  }

//+------------------------------------------------------------------+
//| Place a pending order with full validation                       |
//+------------------------------------------------------------------+
bool PlacePending(int cmd, double price, double sl, double tp)
  {
   price = NormalizeDouble(price, Digits);
   sl    = NormalizeDouble(sl, Digits);
   tp    = NormalizeDouble(tp, Digits);

   int    dirSign = (cmd == OP_BUYLIMIT || cmd == OP_BUYSTOP) ? 1 : -1;

   // Enforce minimum R:R before doing anything else.
   if(!PassesRR(price, sl, tp))
      return(false);

   double slDist = MathAbs(price - sl);
   double lots   = CalculateLotSize(slDist, (dirSign > 0 ? OP_BUY : OP_SELL), price);
   if(lots <= 0.0)
      return(false);

   datetime expiry = 0;
   if(PendingExpiryBars > 0)
      expiry = Time[0] + PendingExpiryBars * PeriodSeconds(PERIOD_M15);

   int ticket = OrderSend(Symbol(), cmd, lots, price, SlippagePoints, sl, tp,
                          TradeComment, MagicNumber, expiry, clrNONE);
   if(ticket < 0)
     {
      PrintFormat("FVR: OrderSend(%d) failed err=%d price=%.*f sl=%.*f tp=%.*f lots=%.2f",
                  cmd, GetLastError(), Digits, price, Digits, sl, Digits, tp, lots);
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| Range trading: BUYLIMIT at lower boundary, SELLLIMIT at upper     |
//+------------------------------------------------------------------+
void ManageRangeOrders()
  {
   // Do not stack: one buy-limit and one sell-limit at a time.
   bool haveBuyLimit  = (CountMyOrders(OP_BUYLIMIT)  > 0);
   bool haveSellLimit = (CountMyOrders(OP_SELLLIMIT) > 0);

   double rangeHeight = g_rangeUpper - g_rangeLower;
   if(rangeHeight <= 0.0)
      return;

   double buffer = TouchTolerancePts * g_pip;

   // --- BUY LIMIT at the validated lower boundary ---
   if(!haveBuyLimit)
     {
      double entry = g_rangeLower;
      double sl    = g_rangeLower - rangeHeight * 0.5 - buffer; // below the box
      double tp    = ComputeTakeProfit(entry, +1);
      if(tp <= 0.0)
         tp = g_rangeUpper;                                     // opposite boundary
      // Enforce structural TP: if required TP for 1:3 exceeds the next zone, abort.
      if(PassesRR(entry, sl, tp))
         PlacePending(OP_BUYLIMIT, entry, sl, tp);
     }

   // --- SELL LIMIT at the validated upper boundary ---
   if(!haveSellLimit)
     {
      double entry = g_rangeUpper;
      double sl    = g_rangeUpper + rangeHeight * 0.5 + buffer; // above the box
      double tp    = ComputeTakeProfit(entry, -1);
      if(tp <= 0.0)
         tp = g_rangeLower;
      if(PassesRR(entry, sl, tp))
         PlacePending(OP_SELLLIMIT, entry, sl, tp);
     }
  }

//+------------------------------------------------------------------+
//| Breakout state machine                                           |
//| 1) Ignore the initial breakout candle.                           |
//| 2) Require a close outside the zone.                             |
//| 3) Price retraces to touch the exterior of the boundary.         |
//| 4) A new M15 fractal forms.                                      |
//| 5) Place BUYSTOP / SELLSTOP slightly beyond that new fractal.    |
//+------------------------------------------------------------------+
void ManageBreakoutStateMachine()
  {
   double buffer = PendingBufferPts * g_pip;
   double tol    = TouchTolerancePts * g_pip;

   // Evaluate on the just-closed candle (index 1).
   double c1 = Close[1];

   switch(g_boState)
     {
      case BO_IDLE:
        {
         if(c1 > g_rangeUpper + tol)          // decisive close above
           {
            g_boState    = BO_CLOSED_UP;      // (candle #1 is the ignored breakout candle)
            g_boRetraced = false;
           }
         else if(c1 < g_rangeLower - tol)     // decisive close below
           {
            g_boState    = BO_CLOSED_DN;
            g_boRetraced = false;
           }
         break;
        }

      case BO_CLOSED_UP:
        {
         // Invalidate if price falls back deep inside the range.
         if(c1 < g_rangeUpper - tol)
           {
            g_boState = BO_IDLE;
            break;
           }
         // 3) Retrace: low of a bar returns to touch the exterior of the boundary.
         if(!g_boRetraced && Low[1] <= g_rangeUpper + tol)
            g_boRetraced = true;
         // 4+5) New swing-high fractal above the boundary -> BUYSTOP beyond it.
         if(g_boRetraced && IsFractalHigh(2))
           {
            double frac  = High[2];
            double entry = frac + buffer;
            double sl    = g_rangeUpper - buffer;        // back inside the range
            double tp    = ComputeTakeProfit(entry, +1);
            if(tp <= 0.0)
               tp = entry + g_impulsePts * g_pip;
            if(PassesRR(entry, sl, tp) && CountMyOrders(OP_BUYSTOP) == 0)
              {
               if(PlacePending(OP_BUYSTOP, entry, sl, tp))
                  g_boState = BO_IDLE;   // armed; reset the machine
              }
           }
         break;
        }

      case BO_CLOSED_DN:
        {
         if(c1 > g_rangeLower + tol)
           {
            g_boState = BO_IDLE;
            break;
           }
         if(!g_boRetraced && High[1] >= g_rangeLower - tol)
            g_boRetraced = true;
         if(g_boRetraced && IsFractalLow(2))
           {
            double frac  = Low[2];
            double entry = frac - buffer;
            double sl    = g_rangeLower + buffer;
            double tp    = ComputeTakeProfit(entry, -1);
            if(tp <= 0.0)
               tp = entry - g_impulsePts * g_pip;
            if(PassesRR(entry, sl, tp) && CountMyOrders(OP_SELLSTOP) == 0)
              {
               if(PlacePending(OP_SELLSTOP, entry, sl, tp))
                  g_boState = BO_IDLE;
              }
           }
         break;
        }
     }
  }

//+------------------------------------------------------------------+
//| Stop-Loss lockdown: SL may only move to break-even or profit     |
//+------------------------------------------------------------------+
void EnforceStopLossLockdown()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderMagicNumber() != MagicNumber || OrderSymbol() != Symbol())
         continue;
      int type = OrderType();
      if(type != OP_BUY && type != OP_SELL)
         continue;

      double open   = OrderOpenPrice();
      double curSL  = OrderStopLoss();
      double newSL  = curSL;

      // Trail the SL up to break-even once the trade is at least 1R in profit.
      double slDist = MathAbs(open - (curSL == 0.0 ? open : curSL));
      if(type == OP_BUY)
        {
         double profitDist = Bid - open;
         if(slDist > 0.0 && profitDist >= slDist && curSL < open)
            newSL = open;                       // move to break-even
        }
      else // OP_SELL
        {
         double profitDist = open - Ask;
         if(slDist > 0.0 && profitDist >= slDist && (curSL > open || curSL == 0.0))
            newSL = open;
        }

      if(newSL == curSL)
         continue;

      // LOCKDOWN: reject any attempt that would WIDEN (loosen) the stop.
      if(!IsStopTightening(type, open, curSL, newSL))
        {
         Print("FVR: SL lockdown blocked a widening OrderModify (ticket ",
               OrderTicket(), ").");
         continue;
        }

      newSL = NormalizeDouble(newSL, Digits);
      if(!OrderModify(OrderTicket(), open, newSL, OrderTakeProfit(), 0, clrNONE))
         PrintFormat("FVR: OrderModify failed ticket=%d err=%d", OrderTicket(), GetLastError());
     }
  }

//+------------------------------------------------------------------+
//| True only if newSL is at break-even or deeper in profit than cur |
//+------------------------------------------------------------------+
bool IsStopTightening(int type, double open, double curSL, double newSL)
  {
   if(type == OP_BUY)
     {
      // For a BUY, a higher SL is tighter/safer. Never allow it below the
      // current SL, and never below break-even once we are moving it.
      if(curSL != 0.0 && newSL < curSL)
         return(false);
      if(newSL < open && newSL < curSL)
         return(false);
      return(newSL >= curSL);
     }
   else // OP_SELL
     {
      // For a SELL, a lower SL is tighter/safer.
      if(curSL != 0.0 && newSL > curSL)
         return(false);
      if(newSL > open && curSL != 0.0 && newSL > curSL)
         return(false);
      return(curSL == 0.0 || newSL <= curSL);
     }
  }
//+------------------------------------------------------------------+
