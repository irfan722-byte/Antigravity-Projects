//+------------------------------------------------------------------+
//|                                        GridRecoverySafeEA.mq4     |
//|   FLAT-LOT, HARD-STOP "safe" variant of GridRecoveryEA.          |
//|                                                                  |
//|   Same grid idea (a ladder of same-direction trades that         |
//|   averages the entry and exits the basket at a money target),    |
//|   but with the two things that make the original dangerous       |
//|   removed:                                                       |
//|     1. NO martingale -- every trade is the SAME fixed lot.       |
//|     2. A MANDATORY basket hard stop in money, plus a mandatory   |
//|        per-trade stop-loss, so a runaway trend cannot compound    |
//|        into a margin call.                                       |
//|                                                                  |
//|   Risk is therefore linear and bounded: worst case is roughly    |
//|   (per-trade SL x MaxTrades) or BasketSLMoney, whichever hits     |
//|   first. Still DEMO-first -- a bounded loss is still a loss.      |
//+------------------------------------------------------------------+
#property copyright "Educational example"
#property version   "1.00"
#property strict

enum ENUM_GRID_DIRECTION
  {
   GRID_BUY_ONLY  = 0,  // Buy grid (buys dips)
   GRID_SELL_ONLY = 1   // Sell grid (sells rallies)
  };

//==================== Inputs ========================================
input string  s1              = "--- Entry (flat lots) ---"; // ---
input ENUM_GRID_DIRECTION Direction = GRID_BUY_ONLY;   // Grid direction
input double  FixedLots       = 0.01;                  // SAME lot for every trade (no martingale)
input int     MaxTrades       = 8;                     // Max trades in the grid

input string  s2              = "--- Grid ---";        // ---
input double  GridStepPoints  = 400;                   // Distance between grid levels (points)

input string  s3              = "--- Exit (all mandatory) ---"; // ---
input double  BasketTPMoney   = 5.0;                   // Close whole basket at this $ profit
input double  BasketSLMoney   = 50.0;                  // HARD basket loss cut in $ (must be > 0)
input double  StopLossPoints  = 1500;                  // Per-trade hard SL in points (must be > 0)

input string  s4              = "--- Filters / misc ---"; // ---
input int     MagicNumber     = 424243;                // Magic number (EA id)
input int     SlippagePoints  = 30;                    // Max slippage (points)
input double  MaxSpreadPoints = 0;                     // Skip entries above this spread (0 = off)

//==================== Globals =======================================
double g_point;
int    g_digits;

//+------------------------------------------------------------------+
int OnInit()
  {
   g_digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   g_point  = MarketInfo(Symbol(), MODE_POINT);

   // Enforce the "safe" contract: refuse to run without hard stops.
   if(BasketSLMoney <= 0.0 || StopLossPoints <= 0.0)
     {
      Print("GridRecoverySafeEA: BasketSLMoney and StopLossPoints must both be > 0. Aborting.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   Print("GridRecoverySafeEA started on ", Symbol(),
         " -- flat lots, hard stops. DEMO-first.");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason) { }

//+------------------------------------------------------------------+
void OnTick()
  {
   if(ManageBasket())
      return;
   MaybeOpenTrade();
  }

//+------------------------------------------------------------------+
int CountTrades(double &basketProfit, double &lastPrice)
  {
   int    count = 0;
   basketProfit = 0.0;
   lastPrice    = 0.0;
   datetime newest = 0;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol())                   continue;
      if(OrderMagicNumber() != MagicNumber)           continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;

      count++;
      basketProfit += OrderProfit() + OrderSwap() + OrderCommission();

      if(OrderOpenTime() >= newest)
        {
         newest    = OrderOpenTime();
         lastPrice = OrderOpenPrice();
        }
     }
   return(count);
  }

//+------------------------------------------------------------------+
void CloseBasket()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol())                   continue;
      if(OrderMagicNumber() != MagicNumber)           continue;

      double price = 0.0;
      if(OrderType() == OP_BUY)  price = MarketInfo(Symbol(), MODE_BID);
      if(OrderType() == OP_SELL) price = MarketInfo(Symbol(), MODE_ASK);
      if(price == 0.0) continue;

      if(!OrderClose(OrderTicket(), OrderLots(), price, SlippagePoints, clrOrange))
         Print("OrderClose failed #", OrderTicket(), " err=", GetLastError());
     }
  }

//+------------------------------------------------------------------+
bool ManageBasket()
  {
   double basketProfit, lastPrice;
   int n = CountTrades(basketProfit, lastPrice);
   if(n == 0) return(false);

   if(BasketTPMoney > 0 && basketProfit >= BasketTPMoney)
     {
      Print("Basket TP hit: +", DoubleToString(basketProfit, 2));
      CloseBasket();
      return(true);
     }
   if(basketProfit <= -BasketSLMoney)   // mandatory
     {
      Print("Basket hard SL hit: ", DoubleToString(basketProfit, 2));
      CloseBasket();
      return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
double NormalizeLots(double lots)
  {
   double minLot  = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot  = MarketInfo(Symbol(), MODE_MAXLOT);
   double lotStep = MarketInfo(Symbol(), MODE_LOTSTEP);
   if(lotStep <= 0) lotStep = 0.01;

   lots = MathFloor(lots / lotStep + 0.5) * lotStep;
   if(lots < minLot) lots = minLot;
   if(lots > maxLot) lots = maxLot;
   return(lots);
  }

//+------------------------------------------------------------------+
void MaybeOpenTrade()
  {
   double basketProfit, lastPrice;
   int n = CountTrades(basketProfit, lastPrice);
   if(n >= MaxTrades) return;

   if(MaxSpreadPoints > 0)
     {
      double spread = (MarketInfo(Symbol(), MODE_ASK) - MarketInfo(Symbol(), MODE_BID)) / g_point;
      if(spread > MaxSpreadPoints) return;
     }

   bool   isBuy = (Direction == GRID_BUY_ONLY);
   double ask   = MarketInfo(Symbol(), MODE_ASK);
   double bid   = MarketInfo(Symbol(), MODE_BID);

   if(n == 0)
     {
      OpenMarket(isBuy, NormalizeLots(FixedLots));
      return;
     }

   double step = GridStepPoints * g_point;
   bool   addLevel = false;
   if(isBuy) { if(ask <= lastPrice - step) addLevel = true; }
   else      { if(bid >= lastPrice + step) addLevel = true; }
   if(!addLevel) return;

   OpenMarket(isBuy, NormalizeLots(FixedLots)); // FLAT lot, never scaled
  }

//+------------------------------------------------------------------+
void OpenMarket(bool isBuy, double lots)
  {
   for(int attempt = 0; attempt < 3; attempt++)
     {
      double price = isBuy ? MarketInfo(Symbol(), MODE_ASK)
                           : MarketInfo(Symbol(), MODE_BID);
      int    type  = isBuy ? OP_BUY : OP_SELL;
      color  clr   = isBuy ? clrBlue : clrRed;

      // Mandatory per-trade stop-loss (respects broker min stop distance).
      double slDist = StopLossPoints * g_point;
      double minStop = MarketInfo(Symbol(), MODE_STOPLEVEL) * g_point;
      if(slDist < minStop) slDist = minStop;
      double sl = isBuy ? price - slDist : price + slDist;
      sl = NormalizeDouble(sl, g_digits);

      int ticket = OrderSend(Symbol(), type, lots, price, SlippagePoints,
                             sl, 0, "GridRecoverySafeEA", MagicNumber, 0, clr);
      if(ticket >= 0)
        {
         Print("Opened ", (isBuy ? "BUY " : "SELL "), DoubleToString(lots, 2),
               " @ ", DoubleToString(price, g_digits),
               " SL ", DoubleToString(sl, g_digits));
         return;
        }

      int err = GetLastError();
      Print("OrderSend failed err=", err, " attempt=", attempt + 1);
      if(err == 134 || err == 148) return;
      Sleep(300);
      RefreshRates();
     }
  }
//+------------------------------------------------------------------+
