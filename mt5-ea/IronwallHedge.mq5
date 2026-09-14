//+------------------------------------------------------------------+
//|                                              IronwallHedge.mq5    |
//|   Moving-grid martingale hedge EA for MetaTrader 5                |
//|                                                                  |
//|   Strategy (as specified by the user):                           |
//|     * First trade of a cycle: market BUY at the base lot. Its     |
//|       price is the cycle anchor.                                  |
//|     * The grid then FOLLOWS price. Every time price extends one   |
//|       more grid step beyond the furthest level already traded:    |
//|         - a new step UP    -> add a BUY   (in the move direction) |
//|         - a new step DOWN  -> add a SELL  (in the move direction) |
//|       Each new entry DOUBLES the lot: 0.01, 0.02, 0.04, 0.08 ...  |
//|       Adds keep coming as price keeps moving -- it does NOT stop  |
//|       or freeze -- until the basket turns net profit.             |
//|     * Basket exit: watch the combined floating P/L of all trades. |
//|       When it reaches the trail-start target (default $2) a       |
//|       trailing lock arms; if profit then falls back by the trail  |
//|       gap (default $1) from its peak, ALL trades close.           |
//|     * MANDATORY account stop: if the basket's floating loss ever  |
//|       reaches StopLossPct of the account balance (default 50%),   |
//|       everything is closed. This is the only thing standing       |
//|       between a bad trend and a wiped account -- do not remove it. |
//|     * When the basket closes (profit OR stop), a new cycle starts |
//|       immediately at the current price. No spread filter.         |
//|                                                                  |
//|   RISK WARNING: This is a martingale with NO per-trade stop. Lot  |
//|   sizes grow geometrically as price trends. A sustained move will  |
//|   hit the StopLossPct floor and realise a large loss -- that is   |
//|   the design working, not a bug. There is no lot schedule that    |
//|   "always turns net profit" on a finite account. Test on DEMO.    |
//|   Educational use only. Not financial advice.                    |
//+------------------------------------------------------------------+
#property copyright   "Educational reconstruction"
#property link        ""
#property version     "3.00"
#property description "Moving-grid martingale: doubles lots on each new price step until net profit; mandatory equity stop. High risk; demo-test first."

#include <Trade/Trade.mqh>
#include <Trade/PositionInfo.mqh>

enum ENUM_START_DIRECTION
  {
   START_BUY  = 0,   // First trade = BUY
   START_SELL = 1    // First trade = SELL
  };

//============================ INPUTS ================================
input group           "=== General ==="
input long            InpMagic          = 490051;          // Magic number
input string          InpComment        = "IronwallHedge"; // Order comment
input ulong           InpSlippage       = 50;              // Max slippage (points)

input group           "=== Entry & grid ==="
input ENUM_START_DIRECTION InpStartDir  = START_BUY;       // First trade direction
input double          InpInitialLot     = 0.01;            // Base (first) lot
input double          InpLotMultiplier  = 2.0;             // Lot multiplier per new entry
input double          InpMaxLot         = 100.0;           // Hard cap on a single order lot
input double          InpGridStepPrice  = 2.0;             // Grid step (price, e.g. 2.0 = $2)
input int             InpMaxLevels      = 100;             // Absolute max entries per cycle

input group           "=== Basket exit (net profit + trailing) ==="
input double          InpTrailStartMoney= 2.0;             // Arm trailing when basket profit >= this (money)
input double          InpTrailGapMoney  = 1.0;             // Close if profit falls this much from its peak (money)

input group           "=== MANDATORY account stop ==="
input double          InpStopLossPct    = 50.0;            // Close basket when floating loss >= this % of balance

input group           "=== Display ==="
input bool            InpShowPanel      = true;            // Show on-chart status panel
input bool            InpDrawLines      = true;            // Draw next buy/sell trigger lines
//===================================================================

CTrade         trade;
CPositionInfo  posinfo;

double         g_point;
double         g_ticksize;

bool           g_trailActive = false;
double         g_peakProfit  = 0.0;

string         LINE_UP   = "IWH_next_buy";
string         LINE_DN   = "IWH_next_sell";

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
   if(InpStopLossPct <= 0.0)     { Print("ERROR: InpStopLossPct must be > 0");     return(INIT_PARAMETERS_INCORRECT); }

   SyncTrailStateFromBasket();

   Print("IronwallHedge v3 initialized on ", _Symbol,
         " | step=", InpGridStepPrice, " base=", InpInitialLot,
         " mult=", InpLotMultiplier, " stop=", InpStopLossPct, "%");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Comment("");
   ObjectDelete(0, LINE_UP);
   ObjectDelete(0, LINE_DN);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   int count = CountPositions();

   //--- 1) Flat -> start a fresh cycle at once (no spread filter)
   if(count == 0)
     {
      ResetTrailState();
      StartNewCycle();
      if(InpShowPanel) UpdatePanel(CountPositions(), 0.0);
      return;
     }

   double profit  = BasketFloatingPL();
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);

   //--- 2) MANDATORY account stop
   if(balance > 0.0 && profit <= -(InpStopLossPct / 100.0) * balance)
     {
      Print("ACCOUNT STOP hit. loss=", DoubleToString(profit,2),
            " (", DoubleToString(InpStopLossPct,1), "% of ", DoubleToString(balance,2), ")");
      CloseBasket();
      ResetTrailState();
      return;
     }

   //--- 3) Basket exit: net-profit trailing lock
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

   //--- 4) Keep adding doubled lots as price extends
   if(count < InpMaxLevels)
      AddOnExtension(count);

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
//| Add a doubled lot when price extends one step beyond the         |
//| furthest level already traded, in the direction of the move.     |
//+------------------------------------------------------------------+
void AddOnExtension(int count)
  {
   double anchor, maxBuy, minSell;
   if(!GetGridRefs(anchor, maxBuy, minSell))
      return;

   double refUp = (maxBuy  > 0.0) ? maxBuy  : anchor;   // highest price with a BUY
   double refDn = (minSell > 0.0) ? minSell : anchor;   // lowest  price with a SELL

   double step      = InpGridStepPrice;
   double nextBuyAt  = NormalizePrice(refUp + step);
   double nextSellAt = NormalizePrice(refDn - step);

   if(InpDrawLines) DrawLines(nextBuyAt, nextSellAt);

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double lot = NormalizeLot(InpInitialLot * MathPow(InpLotMultiplier, count));

   if(ask >= nextBuyAt)
     {
      if(trade.Buy(lot, _Symbol, ask, 0.0, 0.0, InpComment))
         Print("Add BUY lvl=", count+1, " lot=", lot, " @", DoubleToString(ask,_Digits));
      else
         Print("Add BUY failed lvl=", count+1, " lot=", lot,
               " retcode=", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
     }
   else if(bid <= nextSellAt)
     {
      if(trade.Sell(lot, _Symbol, bid, 0.0, 0.0, InpComment))
         Print("Add SELL lvl=", count+1, " lot=", lot, " @", DoubleToString(bid,_Digits));
      else
         Print("Add SELL failed lvl=", count+1, " lot=", lot,
               " retcode=", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
     }
  }

//+------------------------------------------------------------------+
//| Gather grid reference prices from open positions                 |
//|  anchor  = oldest position open price                            |
//|  maxBuy  = highest open price among BUY positions (0 if none)    |
//|  minSell = lowest  open price among SELL positions (0 if none)   |
//+------------------------------------------------------------------+
bool GetGridRefs(double &anchor, double &maxBuy, double &minSell)
  {
   anchor  = 0.0; maxBuy = 0.0; minSell = 0.0;
   ulong    oldestTicket = 0;
   datetime oldestTime   = 0;
   bool     found        = false;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!posinfo.SelectByTicket(ticket)) continue;
      if(posinfo.Symbol() != _Symbol) continue;
      if(posinfo.Magic()  != InpMagic) continue;

      double op = posinfo.PriceOpen();
      datetime t = (datetime)posinfo.Time();

      if(!found || t < oldestTime) { oldestTime = t; oldestTicket = ticket; found = true; }

      if(posinfo.PositionType() == POSITION_TYPE_BUY)
        {
         if(maxBuy == 0.0 || op > maxBuy) maxBuy = op;
        }
      else
        {
         if(minSell == 0.0 || op < minSell) minSell = op;
        }
     }
   if(!found) return(false);
   if(posinfo.SelectByTicket(oldestTicket))
      anchor = posinfo.PriceOpen();
   return(anchor > 0.0);
  }

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
void SyncTrailStateFromBasket()
  {
   if(CountPositions() == 0) { ResetTrailState(); return; }
   double profit = BasketFloatingPL();
   if(profit >= InpTrailStartMoney) { g_trailActive = true; g_peakProfit = profit; }
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
void DrawLines(double buyAt, double sellAt)
  {
   if(ObjectFind(0, LINE_UP) < 0) ObjectCreate(0, LINE_UP, OBJ_HLINE, 0, 0, buyAt);
   ObjectSetDouble (0, LINE_UP, OBJPROP_PRICE, buyAt);
   ObjectSetInteger(0, LINE_UP, OBJPROP_COLOR, clrDodgerBlue);
   ObjectSetInteger(0, LINE_UP, OBJPROP_STYLE, STYLE_DOT);

   if(ObjectFind(0, LINE_DN) < 0) ObjectCreate(0, LINE_DN, OBJ_HLINE, 0, 0, sellAt);
   ObjectSetDouble (0, LINE_DN, OBJPROP_PRICE, sellAt);
   ObjectSetInteger(0, LINE_DN, OBJPROP_COLOR, clrTomato);
   ObjectSetInteger(0, LINE_DN, OBJPROP_STYLE, STYLE_DOT);
  }

//+------------------------------------------------------------------+
void UpdatePanel(int count, double profit)
  {
   string cur     = AccountInfoString(ACCOUNT_CURRENCY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double stopAt  = -(InpStopLossPct / 100.0) * balance;
   double nextLot = NormalizeLot(InpInitialLot * MathPow(InpLotMultiplier, MathMax(count,1)));

   string txt =
      "IRONWALL HEDGE v3  (" + _Symbol + ")\n" +
      "-------------------------------\n" +
      "Open trades : " + IntegerToString(count) + " / " + IntegerToString(InpMaxLevels) + "\n" +
      "Basket P/L  : " + DoubleToString(profit, 2) + " " + cur + "\n" +
      "Account stop: " + DoubleToString(stopAt, 2) + " " + cur +
                         "  (" + DoubleToString(InpStopLossPct,0) + "% of bal)\n" +
      "Trail       : " + (g_trailActive ? ("ARMED peak=" + DoubleToString(g_peakProfit,2)) : "off") +
                         "  (start " + DoubleToString(InpTrailStartMoney,2) + " / gap " + DoubleToString(InpTrailGapMoney,2) + ")\n" +
      "Next lot    : " + DoubleToString(nextLot, 2) + "\n" +
      "Base x mult : " + DoubleToString(InpInitialLot,2) + " x" + DoubleToString(InpLotMultiplier,2) + "\n" +
      "Grid step   : " + DoubleToString(InpGridStepPrice, _Digits);
   Comment(txt);
  }
//+------------------------------------------------------------------+
