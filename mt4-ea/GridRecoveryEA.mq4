//+------------------------------------------------------------------+
//|                                             GridRecoveryEA.mq4    |
//|   Educational grid + martingale Expert Advisor for MetaTrader 4  |
//|                                                                  |
//|   This EA reproduces the STYLE of strategy shown in typical      |
//|   "US30 EA" marketing videos: a ladder (grid) of trades in one   |
//|   direction, averaging the entry price down, with an optional    |
//|   martingale lot multiplier and a basket take-profit that closes |
//|   every open trade once the floating profit of the basket        |
//|   reaches a target.                                              |
//|                                                                  |
//|   >>> READ THIS <<<                                              |
//|   Grid/martingale systems show near-perfect equity curves in a   |
//|   backtest because an open grid is almost always "temporarily"   |
//|   losing and eventually recovers on a bounce. On a real, strong  |
//|   trend the grid keeps adding losing trades until margin runs    |
//|   out and the account is wiped. Backtest profit here is NOT      |
//|   evidence of live profitability. Use on DEMO only.              |
//+------------------------------------------------------------------+
#property copyright "Educational example"
#property version   "1.00"
#property strict

//--- Direction the grid trades in
enum ENUM_GRID_DIRECTION
  {
   GRID_BUY_ONLY  = 0,  // Buy grid (buys dips) -- matches the video
   GRID_SELL_ONLY = 1   // Sell grid (sells rallies)
  };

//==================== Inputs ========================================
input string  s1              = "--- Entry ---";       // ---
input ENUM_GRID_DIRECTION Direction = GRID_BUY_ONLY;   // Grid direction
input double  StartLots       = 0.01;                  // First trade lot size
input int     MaxTrades       = 15;                    // Max trades in the grid

input string  s2              = "--- Grid ---";        // ---
input double  GridStepPoints  = 300;                   // Distance between grid levels (points)
input double  LotMultiplier   = 1.5;                   // Martingale multiplier (1.0 = flat lots)
input bool    UseGeometricStep= false;                 // Widen the grid step as it grows
input double  StepMultiplier  = 1.2;                   // Step growth factor (if above = true)

input string  s3              = "--- Exit ---";        // ---
input double  BasketTPMoney   = 5.0;                    // Close whole basket at this $ profit
input double  BasketSLMoney   = 0.0;                    // Hard $ loss cut for basket (0 = off)

input string  s4              = "--- Filters / misc ---"; // ---
input int     MagicNumber     = 424242;                // Magic number (EA id)
input int     SlippagePoints  = 30;                    // Max slippage (points)
input double  MaxSpreadPoints = 0;                     // Skip new entries above this spread (0 = off)

//==================== Globals =======================================
double g_point;      // normalized point (handles 3/5-digit brokers)
int    g_digits;

//+------------------------------------------------------------------+
int OnInit()
  {
   g_digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   g_point  = MarketInfo(Symbol(), MODE_POINT);
   // On 3/5-digit brokers one "pip" is 10 points; grid inputs are in
   // raw points so no adjustment is forced, but we expose g_point.
   Print("GridRecoveryEA started on ", Symbol(),
         "  DEMO USE ONLY -- martingale can wipe an account.");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason) { }

//+------------------------------------------------------------------+
void OnTick()
  {
   // 1) Manage the currently open basket (take profit / stop loss).
   if(ManageBasket())
      return; // basket was just closed this tick; wait for next tick

   // 2) Decide whether to add a trade to the grid.
   MaybeOpenTrade();
  }

//+------------------------------------------------------------------+
//| Count our own open trades and sum their floating P/L.            |
//+------------------------------------------------------------------+
int CountTrades(double &basketProfit, double &lastPrice, double &lastLots)
  {
   int    count = 0;
   basketProfit = 0.0;
   lastPrice    = 0.0;
   lastLots     = 0.0;
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
         lastLots  = OrderLots();
        }
     }
   return(count);
  }

//+------------------------------------------------------------------+
//| Close every trade in our basket.                                 |
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
//| If basket hit its money target/stop, close it. Returns true if   |
//| we closed something this tick.                                   |
//+------------------------------------------------------------------+
bool ManageBasket()
  {
   double basketProfit, lastPrice, lastLots;
   int n = CountTrades(basketProfit, lastPrice, lastLots);
   if(n == 0) return(false);

   if(BasketTPMoney > 0 && basketProfit >= BasketTPMoney)
     {
      Print("Basket TP hit: +", DoubleToString(basketProfit, 2));
      CloseBasket();
      return(true);
     }
   if(BasketSLMoney > 0 && basketProfit <= -BasketSLMoney)
     {
      Print("Basket SL hit: ", DoubleToString(basketProfit, 2));
      CloseBasket();
      return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| Normalize a lot size to the broker's volume constraints.         |
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
//| Open the first trade, or add the next grid level.                |
//+------------------------------------------------------------------+
void MaybeOpenTrade()
  {
   double basketProfit, lastPrice, lastLots;
   int n = CountTrades(basketProfit, lastPrice, lastLots);

   if(n >= MaxTrades) return; // grid full -- do not add more risk

   // Optional spread filter.
   if(MaxSpreadPoints > 0)
     {
      double spread = (MarketInfo(Symbol(), MODE_ASK) - MarketInfo(Symbol(), MODE_BID)) / g_point;
      if(spread > MaxSpreadPoints) return;
     }

   bool   isBuy = (Direction == GRID_BUY_ONLY);
   double ask   = MarketInfo(Symbol(), MODE_ASK);
   double bid   = MarketInfo(Symbol(), MODE_BID);

   // --- First trade of a fresh basket ---
   if(n == 0)
     {
      OpenMarket(isBuy, NormalizeLots(StartLots));
      return;
     }

   // --- Add a grid level only after price moved GridStep against us ---
   double step = CurrentStepPoints(n) * g_point;
   bool   addLevel = false;

   if(isBuy)
     {
      // Buy grid averages DOWN: add when price falls a step below last entry.
      if(ask <= lastPrice - step) addLevel = true;
     }
   else
     {
      // Sell grid averages UP: add when price rises a step above last entry.
      if(bid >= lastPrice + step) addLevel = true;
     }

   if(!addLevel) return;

   double nextLots = NormalizeLots(lastLots * LotMultiplier);
   OpenMarket(isBuy, nextLots);
  }

//+------------------------------------------------------------------+
//| Grid step for the n-th existing trade (optionally geometric).    |
//+------------------------------------------------------------------+
double CurrentStepPoints(int existingTrades)
  {
   if(!UseGeometricStep) return(GridStepPoints);
   double step = GridStepPoints;
   for(int i = 1; i < existingTrades; i++) step *= StepMultiplier;
   return(step);
  }

//+------------------------------------------------------------------+
//| Send a market order with a couple of retries.                    |
//+------------------------------------------------------------------+
void OpenMarket(bool isBuy, double lots)
  {
   for(int attempt = 0; attempt < 3; attempt++)
     {
      double price = isBuy ? MarketInfo(Symbol(), MODE_ASK)
                           : MarketInfo(Symbol(), MODE_BID);
      int    type  = isBuy ? OP_BUY : OP_SELL;
      color  clr   = isBuy ? clrBlue : clrRed;

      int ticket = OrderSend(Symbol(), type, lots, price, SlippagePoints,
                             0, 0, "GridRecoveryEA", MagicNumber, 0, clr);
      if(ticket >= 0)
        {
         Print("Opened ", (isBuy ? "BUY " : "SELL "), DoubleToString(lots, 2),
               " @ ", DoubleToString(price, g_digits));
         return;
        }

      int err = GetLastError();
      Print("OrderSend failed err=", err, " attempt=", attempt + 1);
      if(err == 134 /*not enough money*/ || err == 148 /*too many orders*/) return;
      Sleep(300);
      RefreshRates();
     }
  }
//+------------------------------------------------------------------+
