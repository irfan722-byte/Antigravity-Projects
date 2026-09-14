//+------------------------------------------------------------------+
//|                                              IronwallHedge.mq5    |
//|   Hedge / martingale recovery grid Expert Advisor for MetaTrader 5|
//|                                                                  |
//|   Reconstructed from the "IRONWALL HEDGE" strategy demonstrated   |
//|   on XAUUSD M1 in the reference video. The EA:                    |
//|     1. Opens an initial market order (the base position).         |
//|     2. Places an opposite pending STOP order a fixed distance     |
//|        away, with a larger lot (martingale multiplier).           |
//|     3. Each time a pending STOP fills, the net direction flips    |
//|        and a new opposite STOP is placed one grid step further,   |
//|        again with an increased lot -- building a two-sided        |
//|        "wall" that catches price in either direction.             |
//|     4. The whole basket is closed once its combined floating P/L  |
//|        reaches a money target (recovery) or a max-loss limit      |
//|        (the account stop). It then restarts a fresh cycle.        |
//|                                                                  |
//|   RISK WARNING: This is a martingale/grid strategy. Lot sizes     |
//|   grow geometrically. A strong one-directional trend that never   |
//|   retraces, or hitting the broker's margin limit before the       |
//|   basket recovers, can wipe an account. MaxLevels and the account |
//|   stop are the only defence. Test on a DEMO account first and     |
//|   size conservatively. Provided for educational purposes only.    |
//+------------------------------------------------------------------+
#property copyright   "Educational reconstruction"
#property link        ""
#property version     "1.00"
#property description "IRONWALL HEDGE - hedge/martingale recovery grid. Martingale risk applies; demo-test first."

#include <Trade/Trade.mqh>
#include <Trade/PositionInfo.mqh>
#include <Trade/OrderInfo.mqh>

//--- Direction choice for the first order of every cycle
enum ENUM_START_DIRECTION
  {
   START_BUY  = 0,   // Always start with BUY
   START_SELL = 1,   // Always start with SELL
   START_AUTO = 2    // Follow last closed candle (bull=BUY, bear=SELL)
  };

//--- Basket profit target mode
enum ENUM_TP_MODE
  {
   TP_MONEY  = 0,    // Take profit in account currency (money)
   TP_POINTS = 1     // Take profit as net points on the basket
  };

//============================ INPUTS ================================
input group           "=== General ==="
input long            InpMagic          = 490049;      // Magic number
input string          InpComment        = "IronwallHedge"; // Order comment
input ulong           InpSlippage       = 30;          // Max slippage (points)

input group           "=== Entry ==="
input ENUM_START_DIRECTION InpStartDir  = START_BUY;   // Direction of the first order
input double          InpInitialLot     = 0.01;        // Base (initial) lot
input double          InpLotMultiplier  = 2.0;         // Martingale lot multiplier
input double          InpMaxLot         = 5.0;         // Hard cap on any single order lot
input int             InpGridStepPoints = 300;         // Grid step / hedge distance (points)
input int             InpMaxLevels      = 6;           // Max hedge levels (controlled risk)

input group           "=== Basket exit (Strong Defense) ==="
input ENUM_TP_MODE    InpTpMode         = TP_MONEY;    // Take-profit mode for the basket
input double          InpTakeProfitMoney= 5.0;         // Basket TP in money (if TP_MONEY)
input int             InpTakeProfitPts  = 200;         // Basket TP in net points (if TP_POINTS)
input bool            InpUseAccountStop = true;        // Close basket at a max floating loss
input double          InpMaxLossMoney   = 100.0;       // Max basket floating loss (money)
input bool            InpRestartAfterTP = true;        // Start a new cycle after each close

input group           "=== Filters ==="
input bool            InpUseSpreadFilter= true;        // Skip new cycles when spread too wide
input int             InpMaxSpreadPoints= 60;          // Max allowed spread (points)
input bool            InpShowPanel      = true;        // Show on-chart status panel
//===================================================================

CTrade         trade;
CPositionInfo  posinfo;
COrderInfo     ordinfo;

double         g_point;
double         g_ticksize;
long           g_stops_level;   // broker minimum stop distance in points
datetime       g_last_bar_time = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetAsyncMode(false);

   g_point    = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   g_ticksize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(g_ticksize <= 0.0)
      g_ticksize = g_point;
   g_stops_level = (long)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);

   //--- basic sanity checks
   if(InpInitialLot <= 0.0)
     {
      Print("ERROR: InpInitialLot must be > 0");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpLotMultiplier < 1.0)
     {
      Print("ERROR: InpLotMultiplier must be >= 1.0");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpMaxLevels < 1)
     {
      Print("ERROR: InpMaxLevels must be >= 1");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpGridStepPoints <= 0)
     {
      Print("ERROR: InpGridStepPoints must be > 0");
      return(INIT_PARAMETERS_INCORRECT);
     }

   Print("IronwallHedge initialized on ", _Symbol,
         " | point=", g_point, " ticksize=", g_ticksize,
         " stops_level=", g_stops_level);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Comment("");
  }

//+------------------------------------------------------------------+
//| Main tick handler                                                |
//+------------------------------------------------------------------+
void OnTick()
  {
   int    positions = CountPositions();
   int    pendings   = CountPendings();
   double basketPL   = BasketFloatingPL();

   //--- 1) Manage an open basket: check exit conditions first
   if(positions > 0)
     {
      if(BasketShouldClose(basketPL))
        {
         CloseBasket();
         if(InpShowPanel) UpdatePanel(0, 0, 0.0);
         return;
        }

      //--- 2) A pending just filled? Keep exactly one live pending
      //---    until we reach the level cap.
      if(pendings == 0 && positions < InpMaxLevels)
         PlaceNextHedge(positions);

      if(InpShowPanel) UpdatePanel(positions, pendings, basketPL);
      return;
     }

   //--- 3) Flat: clean any orphan pendings then (optionally) start anew
   if(pendings > 0)
      DeleteAllPendings();

   if(!InpRestartAfterTP && HasCycleRunThisBar())
     {
      if(InpShowPanel) UpdatePanel(0, 0, 0.0);
      return;
     }

   if(SpreadOK())
      StartNewCycle();

   if(InpShowPanel) UpdatePanel(CountPositions(), CountPendings(), 0.0);
  }

//+------------------------------------------------------------------+
//| Start a fresh cycle: initial market order + first hedge stop     |
//+------------------------------------------------------------------+
void StartNewCycle()
  {
   bool startBuy = DecideStartBuy();
   double lot    = NormalizeLot(InpInitialLot);

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   bool ok;
   if(startBuy)
      ok = trade.Buy(lot, _Symbol, ask, 0.0, 0.0, InpComment);
   else
      ok = trade.Sell(lot, _Symbol, bid, 0.0, 0.0, InpComment);

   if(!ok)
     {
      Print("StartNewCycle: initial order failed. retcode=", trade.ResultRetcode(),
            " ", trade.ResultRetcodeDescription());
      return;
     }

   g_last_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
   Print("New cycle started. dir=", (startBuy ? "BUY" : "SELL"), " lot=", lot);

   //--- immediately place the level-1 opposite hedge stop
   PlaceNextHedge(1);
  }

//+------------------------------------------------------------------+
//| Place the next hedge STOP order for the given level index.       |
//| level = number of positions that already exist (1-based next).   |
//| Direction alternates: even levels follow the start direction,    |
//| odd levels oppose it.                                            |
//+------------------------------------------------------------------+
void PlaceNextHedge(int level)
  {
   if(level >= InpMaxLevels)
      return;                       // cap reached -> no more hedges

   bool startBuy   = CycleStartWasBuy();
   //--- level 0 = start dir, level 1 = opposite, level 2 = start dir ...
   bool nextIsBuy  = ((level % 2) == 0) ? startBuy : !startBuy;

   double lot = NormalizeLot(InpInitialLot * MathPow(InpLotMultiplier, level));
   double step = InpGridStepPoints * g_point;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double minDist = (double)MathMax(g_stops_level, 1) * g_point;

   bool ok = false;
   if(nextIsBuy)
     {
      //--- BUY STOP above the market
      double price = ask + MathMax(step, minDist);
      price = NormalizePrice(price);
      ok = trade.BuyStop(lot, price, _Symbol, 0.0, 0.0, ORDER_TIME_GTC, 0, InpComment);
     }
   else
     {
      //--- SELL STOP below the market
      double price = bid - MathMax(step, minDist);
      price = NormalizePrice(price);
      ok = trade.SellStop(lot, price, _Symbol, 0.0, 0.0, ORDER_TIME_GTC, 0, InpComment);
     }

   if(!ok)
      Print("PlaceNextHedge failed. level=", level, " lot=", lot,
            " retcode=", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
   else
      Print("Hedge placed. level=", level, " dir=", (nextIsBuy ? "BUYSTOP" : "SELLSTOP"),
            " lot=", lot);
  }

//+------------------------------------------------------------------+
//| Decide whether the current basket should be closed               |
//+------------------------------------------------------------------+
bool BasketShouldClose(double basketPL)
  {
   //--- account / basket stop (Strong Defense)
   if(InpUseAccountStop && basketPL <= -MathAbs(InpMaxLossMoney))
     {
      Print("Basket STOP hit. floatingPL=", DoubleToString(basketPL, 2));
      return(true);
     }

   //--- take profit
   if(InpTpMode == TP_MONEY)
     {
      if(basketPL >= InpTakeProfitMoney)
        {
         Print("Basket TP (money) hit. floatingPL=", DoubleToString(basketPL, 2));
         return(true);
        }
     }
   else // TP_POINTS
     {
      double netPts = BasketNetPoints();
      if(netPts >= InpTakeProfitPts)
        {
         Print("Basket TP (points) hit. netPts=", DoubleToString(netPts, 1));
         return(true);
        }
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| Close every position and pending order that belongs to this EA   |
//+------------------------------------------------------------------+
void CloseBasket()
  {
   //--- close positions
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
   //--- delete pendings
   DeleteAllPendings();
   Print("Basket closed.");
  }

//+------------------------------------------------------------------+
//| Delete all our pending orders                                    |
//+------------------------------------------------------------------+
void DeleteAllPendings()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0) continue;
      if(!ordinfo.Select(ticket)) continue;
      if(ordinfo.Symbol() != _Symbol) continue;
      if(ordinfo.Magic()  != InpMagic) continue;
      if(!trade.OrderDelete(ticket))
         Print("OrderDelete failed ticket=", ticket, " retcode=", trade.ResultRetcode());
     }
  }

//+------------------------------------------------------------------+
//| Count our open positions                                         |
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
//| Count our pending orders                                         |
//+------------------------------------------------------------------+
int CountPendings()
  {
   int n = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0) continue;
      if(!ordinfo.Select(ticket)) continue;
      if(ordinfo.Symbol() == _Symbol && ordinfo.Magic() == InpMagic)
         n++;
     }
   return(n);
  }

//+------------------------------------------------------------------+
//| Sum floating P/L (profit + swap + commission) of our positions   |
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
//| Net profit of the basket expressed in points (volume-weighted)   |
//+------------------------------------------------------------------+
double BasketNetPoints()
  {
   double weightedPts = 0.0;
   double totalVol    = 0.0;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!posinfo.SelectByTicket(ticket)) continue;
      if(posinfo.Symbol() != _Symbol) continue;
      if(posinfo.Magic()  != InpMagic) continue;

      double open = posinfo.PriceOpen();
      double vol  = posinfo.Volume();
      double pts;
      if(posinfo.PositionType() == POSITION_TYPE_BUY)
         pts = (bid - open) / g_point;
      else
         pts = (open - ask) / g_point;
      weightedPts += pts * vol;
      totalVol    += vol;
     }
   if(totalVol <= 0.0) return(0.0);
   return(weightedPts / totalVol);
  }

//+------------------------------------------------------------------+
//| Was the current cycle's first order a BUY? Derived from the      |
//| oldest (lowest-time) of our open positions.                      |
//+------------------------------------------------------------------+
bool CycleStartWasBuy()
  {
   ulong    firstTicket = 0;
   datetime firstTime   = 0;
   bool     found       = false;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!posinfo.SelectByTicket(ticket)) continue;
      if(posinfo.Symbol() != _Symbol) continue;
      if(posinfo.Magic()  != InpMagic) continue;

      datetime t = (datetime)posinfo.Time();
      if(!found || t < firstTime)
        {
         firstTime   = t;
         firstTicket = ticket;
         found       = true;
        }
     }
   if(found && posinfo.SelectByTicket(firstTicket))
      return(posinfo.PositionType() == POSITION_TYPE_BUY);

   //--- fallback to the configured start direction
   return(DecideStartBuy());
  }

//+------------------------------------------------------------------+
//| Decide start direction for a brand new cycle                     |
//+------------------------------------------------------------------+
bool DecideStartBuy()
  {
   if(InpStartDir == START_BUY)  return(true);
   if(InpStartDir == START_SELL) return(false);
   //--- START_AUTO: follow the last completed candle
   double o = iOpen(_Symbol, PERIOD_CURRENT, 1);
   double c = iClose(_Symbol, PERIOD_CURRENT, 1);
   return(c >= o);
  }

//+------------------------------------------------------------------+
//| Spread filter                                                    |
//+------------------------------------------------------------------+
bool SpreadOK()
  {
   if(!InpUseSpreadFilter) return(true);
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread > InpMaxSpreadPoints)
     {
      static datetime lastWarn = 0;
      if(TimeCurrent() - lastWarn > 60)
        {
         Print("Spread too wide (", spread, " > ", InpMaxSpreadPoints, "). Skipping new cycle.");
         lastWarn = TimeCurrent();
        }
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| Guard so we don't reopen many cycles on the same bar when        |
//| InpRestartAfterTP is false.                                      |
//+------------------------------------------------------------------+
bool HasCycleRunThisBar()
  {
   return(g_last_bar_time == iTime(_Symbol, PERIOD_CURRENT, 0));
  }

//+------------------------------------------------------------------+
//| Normalize a lot to the broker's volume constraints               |
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

   //--- round to the step's decimal precision
   int digits = 0;
   double s = step;
   while(s < 1.0 && digits < 8) { s *= 10.0; digits++; }
   return(NormalizeDouble(capped, digits));
  }

//+------------------------------------------------------------------+
//| Normalize a price to the symbol tick size                        |
//+------------------------------------------------------------------+
double NormalizePrice(double price)
  {
   if(g_ticksize <= 0.0)
      return(NormalizeDouble(price, _Digits));
   double p = MathRound(price / g_ticksize) * g_ticksize;
   return(NormalizeDouble(p, _Digits));
  }

//+------------------------------------------------------------------+
//| On-chart status panel                                            |
//+------------------------------------------------------------------+
void UpdatePanel(int positions, int pendings, double basketPL)
  {
   string tp = (InpTpMode == TP_MONEY)
               ? (DoubleToString(InpTakeProfitMoney, 2) + " " + AccountInfoString(ACCOUNT_CURRENCY))
               : (IntegerToString(InpTakeProfitPts) + " pts");
   string txt =
      "IRONWALL HEDGE  (" + _Symbol + ")\n" +
      "-------------------------------\n" +
      "Positions : " + IntegerToString(positions) + " / " + IntegerToString(InpMaxLevels) + "\n" +
      "Pendings  : " + IntegerToString(pendings) + "\n" +
      "Floating  : " + DoubleToString(basketPL, 2) + " " + AccountInfoString(ACCOUNT_CURRENCY) + "\n" +
      "Basket TP : " + tp + "\n" +
      "Stop      : " + (InpUseAccountStop ? ("-" + DoubleToString(InpMaxLossMoney, 2)) : "off") + "\n" +
      "Base lot  : " + DoubleToString(InpInitialLot, 2) + "  x" + DoubleToString(InpLotMultiplier, 2) + "\n" +
      "Grid step : " + IntegerToString(InpGridStepPoints) + " pts";
   Comment(txt);
  }
//+------------------------------------------------------------------+
