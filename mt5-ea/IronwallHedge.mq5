//+------------------------------------------------------------------+
//|                                              IronwallHedge.mq5    |
//|   Two-level pendulum martingale hedge EA for MetaTrader 5         |
//|                                                                  |
//|   Strategy (as specified by the user):                           |
//|     * A cycle is anchored to TWO fixed price gates one grid step  |
//|       apart: a BUY gate (the first entry price, e.g. 4310) and a  |
//|       SELL gate one step below it (e.g. 4308).                    |
//|     * The first trade of a cycle is a market BUY at the base lot. |
//|     * Entries then ALTERNATE at the two gates:                    |
//|         - price falls to the SELL gate  -> open a SELL            |
//|         - price rises to the BUY gate   -> open a BUY             |
//|       Each new entry DOUBLES the lot: 0.01, 0.02, 0.04, 0.08 ...  |
//|     * The whole basket (all buys + sells) is closed together once |
//|       its combined floating profit reaches the trail-start target |
//|       (default $2). After that a trailing lock is armed: if profit |
//|       falls back by the trail gap (default $1) from its peak, the  |
//|       basket is closed, locking in the gain.                      |
//|     * Lots keep doubling until the basket turns profitable, up to  |
//|       a MaxLevels safety cap. When the basket closes, a fresh      |
//|       cycle starts immediately at the current price. No spread    |
//|       filter.                                                     |
//|                                                                  |
//|   RISK WARNING: This is a martingale. Lot sizes grow             |
//|   geometrically. A sustained one-directional trend that keeps     |
//|   round-tripping the two gates will keep doubling the lot and can  |
//|   margin-call the account before the +$2 target is reached. The    |
//|   MaxLevels cap and the optional hard money stop are the only      |
//|   defence. Test on a DEMO account first. Educational use only.    |
//+------------------------------------------------------------------+
#property copyright   "Educational reconstruction"
#property link        ""
#property version     "2.00"
#property description "Two-level pendulum martingale. Buy/sell gates, lot doubling, basket net-profit trail. Martingale risk; demo-test first."

#include <Trade/Trade.mqh>
#include <Trade/PositionInfo.mqh>

//--- Direction of the first trade of every cycle
enum ENUM_START_DIRECTION
  {
   START_BUY  = 0,   // First trade = BUY (gates: BUY=entry, SELL=entry-step)
   START_SELL = 1    // First trade = SELL (gates: SELL=entry, BUY=entry+step)
  };

//============================ INPUTS ================================
input group           "=== General ==="
input long            InpMagic          = 490050;         // Magic number
input string          InpComment        = "IronwallHedge";// Order comment
input ulong           InpSlippage       = 50;             // Max slippage (points)

input group           "=== Entry & grid ==="
input ENUM_START_DIRECTION InpStartDir  = START_BUY;      // First trade direction
input double          InpInitialLot     = 0.01;           // Base (first) lot
input double          InpLotMultiplier  = 2.0;            // Lot multiplier per re-entry
input double          InpMaxLot         = 50.0;           // Hard cap on a single order lot
input double          InpGridStepPrice  = 2.0;            // Distance between the two gates (price, e.g. 2.0 = $2)
input int             InpMaxLevels      = 15;             // Max entries per cycle (safety cap)

input group           "=== Basket exit (net profit + trailing) ==="
input double          InpTrailStartMoney= 2.0;            // Arm trailing when basket profit >= this (money)
input double          InpTrailGapMoney  = 1.0;            // Close if profit falls this much from its peak (money)

input group           "=== Safety (optional) ==="
input bool            InpUseHardStop    = false;          // Close basket at a max floating loss
input double          InpMaxLossMoney   = 0.0;            // Max basket floating loss (money, if hard stop on)

input group           "=== Display ==="
input bool            InpShowPanel      = true;           // Show on-chart status panel
input bool            InpDrawGates      = true;           // Draw the two gate lines
//===================================================================

CTrade         trade;
CPositionInfo  posinfo;

double         g_point;
double         g_ticksize;
datetime       g_tickGuard = 0;

//--- trailing state (per cycle)
bool           g_trailActive = false;
double         g_peakProfit  = 0.0;

//--- gate line object names
string         GATE_BUY_NAME  = "IWH_gate_buy";
string         GATE_SELL_NAME = "IWH_gate_sell";

//+------------------------------------------------------------------+
int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetAsyncMode(false);

   g_point    = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   g_ticksize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(g_ticksize <= 0.0) g_ticksize = g_point;

   if(InpInitialLot <= 0.0)      { Print("ERROR: InpInitialLot must be > 0");      return(INIT_PARAMETERS_INCORRECT); }
   if(InpLotMultiplier < 1.0)    { Print("ERROR: InpLotMultiplier must be >= 1");  return(INIT_PARAMETERS_INCORRECT); }
   if(InpMaxLevels < 1)          { Print("ERROR: InpMaxLevels must be >= 1");      return(INIT_PARAMETERS_INCORRECT); }
   if(InpGridStepPrice <= 0.0)   { Print("ERROR: InpGridStepPrice must be > 0");   return(INIT_PARAMETERS_INCORRECT); }
   if(InpTrailStartMoney <= 0.0) { Print("ERROR: InpTrailStartMoney must be > 0"); return(INIT_PARAMETERS_INCORRECT); }
   if(InpTrailGapMoney <= 0.0)   { Print("ERROR: InpTrailGapMoney must be > 0");   return(INIT_PARAMETERS_INCORRECT); }

   //--- re-arm trailing state from any basket already open
   SyncTrailStateFromBasket();

   Print("IronwallHedge v2 initialized on ", _Symbol,
         " | step(price)=", InpGridStepPrice,
         " base=", InpInitialLot, " mult=", InpLotMultiplier,
         " maxLevels=", InpMaxLevels);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Comment("");
   ObjectDelete(0, GATE_BUY_NAME);
   ObjectDelete(0, GATE_SELL_NAME);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   int    count  = CountPositions();
   double profit = BasketFloatingPL();

   //--- 1) No open basket -> start a fresh cycle immediately (no spread filter)
   if(count == 0)
     {
      ResetTrailState();
      StartNewCycle();
      if(InpShowPanel) UpdatePanel(CountPositions(), 0.0);
      return;
     }

   //--- 2) Basket exit: trailing net-profit lock
   if(!g_trailActive && profit >= InpTrailStartMoney)
     {
      g_trailActive = true;
      g_peakProfit  = profit;
     }
   if(g_trailActive)
     {
      if(profit > g_peakProfit) g_peakProfit = profit;
      if(profit <= g_peakProfit - InpTrailGapMoney)
        {
         Print("Basket trail close. profit=", DoubleToString(profit,2),
               " peak=", DoubleToString(g_peakProfit,2));
         CloseBasket();
         ResetTrailState();
         return;
        }
     }

   //--- 3) Optional hard money stop
   if(InpUseHardStop && InpMaxLossMoney > 0.0 && profit <= -MathAbs(InpMaxLossMoney))
     {
      Print("Basket hard stop. profit=", DoubleToString(profit,2));
      CloseBasket();
      ResetTrailState();
      return;
     }

   //--- 4) Add the next martingale entry when a gate is touched
   ManageGridEntries(count);

   if(InpShowPanel) UpdatePanel(count, profit);
  }

//+------------------------------------------------------------------+
//| Open the first trade of a new cycle at market                    |
//+------------------------------------------------------------------+
void StartNewCycle()
  {
   double lot = NormalizeLot(InpInitialLot);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   bool ok;
   if(InpStartDir == START_BUY)
      ok = trade.Buy(lot, _Symbol, ask, 0.0, 0.0, InpComment);
   else
      ok = trade.Sell(lot, _Symbol, bid, 0.0, 0.0, InpComment);

   if(!ok)
      Print("StartNewCycle failed. retcode=", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
   else
      Print("New cycle. first=", (InpStartDir==START_BUY?"BUY":"SELL"), " lot=", lot);
  }

//+------------------------------------------------------------------+
//| Add the next entry when price reaches the appropriate gate       |
//+------------------------------------------------------------------+
void ManageGridEntries(int count)
  {
   if(count >= InpMaxLevels)
     {
      if(InpDrawGates) DrawGates();
      return;                       // cap reached: hold, wait for the basket to recover
     }

   //--- anchor = the oldest position of the cycle (the first entry)
   bool   anchorIsBuy;
   double anchorOpen;
   if(!GetAnchor(anchorOpen, anchorIsBuy))
      return;

   double gateBuy, gateSell;
   bool   nextIsBuy;
   if(anchorIsBuy)
     {
      gateBuy   = anchorOpen;                    // buy gate = first entry price
      gateSell  = anchorOpen - InpGridStepPrice; // sell gate one step below
      nextIsBuy = ((count % 2) == 0);            // buy,sell,buy,sell...
     }
   else
     {
      gateSell  = anchorOpen;                    // sell gate = first entry price
      gateBuy   = anchorOpen + InpGridStepPrice; // buy gate one step above
      nextIsBuy = ((count % 2) == 1);            // sell,buy,sell,buy...
     }

   if(InpDrawGates) DrawGates(gateBuy, gateSell);

   double nextLot = NormalizeLot(InpInitialLot * MathPow(InpLotMultiplier, count));
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(nextIsBuy)
     {
      //--- price has risen back to (or above) the BUY gate
      if(ask >= NormalizePrice(gateBuy))
        {
         if(trade.Buy(nextLot, _Symbol, ask, 0.0, 0.0, InpComment))
            Print("Add BUY lvl=", count+1, " lot=", nextLot, " @gate=", DoubleToString(gateBuy,_Digits));
         else
            Print("Add BUY failed. retcode=", trade.ResultRetcode());
        }
     }
   else
     {
      //--- price has fallen to (or below) the SELL gate
      if(bid <= NormalizePrice(gateSell))
        {
         if(trade.Sell(nextLot, _Symbol, bid, 0.0, 0.0, InpComment))
            Print("Add SELL lvl=", count+1, " lot=", nextLot, " @gate=", DoubleToString(gateSell,_Digits));
         else
            Print("Add SELL failed. retcode=", trade.ResultRetcode());
        }
     }
  }

//+------------------------------------------------------------------+
//| Find the oldest position of the cycle (its open price and side)  |
//+------------------------------------------------------------------+
bool GetAnchor(double &openPrice, bool &isBuy)
  {
   ulong    bestTicket = 0;
   datetime bestTime   = 0;
   bool     found      = false;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!posinfo.SelectByTicket(ticket)) continue;
      if(posinfo.Symbol() != _Symbol) continue;
      if(posinfo.Magic()  != InpMagic) continue;

      datetime t = (datetime)posinfo.Time();
      if(!found || t < bestTime)
        {
         bestTime   = t;
         bestTicket = ticket;
         found      = true;
        }
     }
   if(!found) return(false);

   if(!posinfo.SelectByTicket(bestTicket)) return(false);
   openPrice = posinfo.PriceOpen();
   isBuy     = (posinfo.PositionType() == POSITION_TYPE_BUY);
   return(true);
  }

//+------------------------------------------------------------------+
//| Close all positions of this EA                                   |
//+------------------------------------------------------------------+
void CloseBasket()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!posinfo.SelectByTicket(ticket)) continue;
      if(posinfo.Symbol() != _Symbol) continue;
      if(posinfo.Magic()  != InpMagic) continue;
      if(!trade.PositionClose(ticket))
         Print("PositionClose failed ticket=", ticket, " retcode=", trade.ResultRetcode());
     }
   Print("Basket closed.");
  }

//+------------------------------------------------------------------+
int CountPositions()
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!posinfo.SelectByTicket(ticket)) continue;
      if(posinfo.Symbol() == _Symbol && posinfo.Magic() == InpMagic)
         n++;
     }
   return(n);
  }

//+------------------------------------------------------------------+
double BasketFloatingPL()
  {
   double pl = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!posinfo.SelectByTicket(ticket)) continue;
      if(posinfo.Symbol() != _Symbol) continue;
      if(posinfo.Magic()  != InpMagic) continue;
      pl += posinfo.Profit() + posinfo.Swap() + posinfo.Commission();
     }
   return(pl);
  }

//+------------------------------------------------------------------+
void ResetTrailState()
  {
   g_trailActive = false;
   g_peakProfit  = 0.0;
  }

//+------------------------------------------------------------------+
//| On (re)start, if a basket is already open and already past the   |
//| trail-start target, arm the trailing so we don't lose the lock.  |
//+------------------------------------------------------------------+
void SyncTrailStateFromBasket()
  {
   if(CountPositions() == 0) { ResetTrailState(); return; }
   double profit = BasketFloatingPL();
   if(profit >= InpTrailStartMoney)
     {
      g_trailActive = true;
      g_peakProfit  = profit;
     }
  }

//+------------------------------------------------------------------+
double NormalizeLot(double lot)
  {
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   double capped = MathMin(lot, InpMaxLot);
   if(step > 0.0)
      capped = MathFloor(capped / step + 1e-9) * step;
   if(capped < minLot) capped = minLot;
   if(capped > maxLot) capped = maxLot;

   int digits = 0; double s = step;
   while(s < 1.0 && digits < 8) { s *= 10.0; digits++; }
   return(NormalizeDouble(capped, digits));
  }

//+------------------------------------------------------------------+
double NormalizePrice(double price)
  {
   if(g_ticksize <= 0.0) return(NormalizeDouble(price, _Digits));
   double p = MathRound(price / g_ticksize) * g_ticksize;
   return(NormalizeDouble(p, _Digits));
  }

//+------------------------------------------------------------------+
void DrawGates(double gateBuy = 0.0, double gateSell = 0.0)
  {
   if(gateBuy > 0.0)
     {
      if(ObjectFind(0, GATE_BUY_NAME) < 0)
         ObjectCreate(0, GATE_BUY_NAME, OBJ_HLINE, 0, 0, gateBuy);
      ObjectSetDouble(0, GATE_BUY_NAME, OBJPROP_PRICE, gateBuy);
      ObjectSetInteger(0, GATE_BUY_NAME, OBJPROP_COLOR, clrDodgerBlue);
      ObjectSetInteger(0, GATE_BUY_NAME, OBJPROP_STYLE, STYLE_DOT);
     }
   if(gateSell > 0.0)
     {
      if(ObjectFind(0, GATE_SELL_NAME) < 0)
         ObjectCreate(0, GATE_SELL_NAME, OBJ_HLINE, 0, 0, gateSell);
      ObjectSetDouble(0, GATE_SELL_NAME, OBJPROP_PRICE, gateSell);
      ObjectSetInteger(0, GATE_SELL_NAME, OBJPROP_COLOR, clrTomato);
      ObjectSetInteger(0, GATE_SELL_NAME, OBJPROP_STYLE, STYLE_DOT);
     }
  }

//+------------------------------------------------------------------+
void UpdatePanel(int count, double profit)
  {
   string cur = AccountInfoString(ACCOUNT_CURRENCY);
   double nextLot = (count < InpMaxLevels)
                    ? NormalizeLot(InpInitialLot * MathPow(InpLotMultiplier, MathMax(count,1)))
                    : 0.0;
   string txt =
      "IRONWALL HEDGE v2  (" + _Symbol + ")\n" +
      "-------------------------------\n" +
      "Open trades : " + IntegerToString(count) + " / " + IntegerToString(InpMaxLevels) + "\n" +
      "Basket P/L  : " + DoubleToString(profit, 2) + " " + cur + "\n" +
      "Trail       : " + (g_trailActive ? ("ARMED peak=" + DoubleToString(g_peakProfit,2)) : "off") +
                         "  (start " + DoubleToString(InpTrailStartMoney,2) + " / gap " + DoubleToString(InpTrailGapMoney,2) + ")\n" +
      "Next lot    : " + DoubleToString(nextLot, 2) + "\n" +
      "Base x mult : " + DoubleToString(InpInitialLot,2) + " x" + DoubleToString(InpLotMultiplier,2) + "\n" +
      "Gate step   : " + DoubleToString(InpGridStepPrice, _Digits) + "\n" +
      "Hard stop   : " + (InpUseHardStop ? ("-" + DoubleToString(InpMaxLossMoney,2)) : "off");
   Comment(txt);
  }
//+------------------------------------------------------------------+
