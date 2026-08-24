//+------------------------------------------------------------------+
//|                                            PendingLadderEA.mq4    |
//|   Places an actual ladder of PENDING orders around price, the    |
//|   way the phone order list in EA_fast.MP4 looked:                |
//|     "US30, buy stop"  ... above the current price                |
//|     "US30, buy limit" ... below the current price                |
//|                                                                  |
//|   While flat, it seeds N buy-stop levels above and N buy-limit   |
//|   levels below, evenly spaced by StepPoints. Whichever direction |
//|   price moves, pendings convert into market buys and stack into  |
//|   one buy basket. The basket is closed as a whole at a money     |
//|   take-profit (and an optional money stop-loss), after which the |
//|   ladder is rebuilt.                                             |
//|                                                                  |
//|   Lots are FLAT by default; set LotMultiplier > 1 to make the    |
//|   outer levels martingale-scaled like the original video (this   |
//|   re-introduces blow-up risk -- demo only).                      |
//+------------------------------------------------------------------+
#property copyright "Educational example"
#property version   "1.00"
#property strict

//==================== Inputs ========================================
input string  s1              = "--- Ladder shape ---";   // ---
input int     LevelsAbove     = 4;                        // # of BUY STOP levels above price
input int     LevelsBelow     = 4;                        // # of BUY LIMIT levels below price
input double  StepPoints      = 300;                      // Spacing between levels (points)
input double  BaseLots        = 0.01;                     // Lot of the nearest level
input double  LotMultiplier   = 1.0;                      // 1.0 = flat; >1 scales outer levels

input string  s2              = "--- Basket exit ---";    // ---
input double  BasketTPMoney   = 5.0;                      // Close all filled trades at this $ profit
input double  BasketSLMoney   = 0.0;                      // Money loss cut for filled basket (0 = off)
input bool    RebuildAfterClose = true;                   // Re-seed the ladder after a basket closes

input string  s3              = "--- Per-order protection ---"; // ---
input double  PerOrderSLPoints = 0;                       // Optional SL on each filled trade (0 = off)
input double  PendingExpiryMin = 0;                       // Auto-expire pendings after N minutes (0 = GTC)

input string  s4              = "--- misc ---";           // ---
input int     MagicNumber     = 424244;                   // Magic number (EA id)
input int     SlippagePoints  = 30;                       // Max slippage (points)

//==================== Globals =======================================
double g_point;
int    g_digits;

//+------------------------------------------------------------------+
int OnInit()
  {
   g_digits = (int)MarketInfo(Symbol(), MODE_DIGITS);
   g_point  = MarketInfo(Symbol(), MODE_POINT);
   Print("PendingLadderEA started on ", Symbol(),
         " -- buy-stop/buy-limit ladder. DEMO-first.");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason) { }

//+------------------------------------------------------------------+
void OnTick()
  {
   int filled, pendings;
   double basketProfit;
   Census(filled, pendings, basketProfit);

   // 1) Manage the filled basket first.
   if(filled > 0)
     {
      if(BasketTPMoney > 0 && basketProfit >= BasketTPMoney)
        {
         Print("Basket TP hit: +", DoubleToString(basketProfit, 2));
         CloseFilled();
         DeletePendings();
         if(RebuildAfterClose) SeedLadder();
         return;
        }
      if(BasketSLMoney > 0 && basketProfit <= -BasketSLMoney)
        {
         Print("Basket money SL hit: ", DoubleToString(basketProfit, 2));
         CloseFilled();
         DeletePendings();
         if(RebuildAfterClose) SeedLadder();
         return;
        }
     }

   // 2) If nothing of ours exists at all, seed the ladder.
   if(filled == 0 && pendings == 0)
      SeedLadder();
  }

//+------------------------------------------------------------------+
//| Count filled market trades, pending orders, and floating P/L.    |
//+------------------------------------------------------------------+
void Census(int &filled, int &pendings, double &basketProfit)
  {
   filled = 0; pendings = 0; basketProfit = 0.0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol())                   continue;
      if(OrderMagicNumber() != MagicNumber)           continue;

      int t = OrderType();
      if(t == OP_BUY || t == OP_SELL)
        {
         filled++;
         basketProfit += OrderProfit() + OrderSwap() + OrderCommission();
        }
      else
         pendings++;
     }
  }

//+------------------------------------------------------------------+
void CloseFilled()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol())                   continue;
      if(OrderMagicNumber() != MagicNumber)           continue;
      int t = OrderType();
      if(t != OP_BUY && t != OP_SELL)                 continue;

      double price = (t == OP_BUY) ? MarketInfo(Symbol(), MODE_BID)
                                   : MarketInfo(Symbol(), MODE_ASK);
      if(!OrderClose(OrderTicket(), OrderLots(), price, SlippagePoints, clrOrange))
         Print("OrderClose failed #", OrderTicket(), " err=", GetLastError());
     }
  }

//+------------------------------------------------------------------+
void DeletePendings()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol())                   continue;
      if(OrderMagicNumber() != MagicNumber)           continue;
      int t = OrderType();
      if(t == OP_BUY || t == OP_SELL)                 continue; // skip filled
      if(!OrderDelete(OrderTicket()))
         Print("OrderDelete failed #", OrderTicket(), " err=", GetLastError());
     }
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
//| Seed the whole ladder: buy stops above, buy limits below.        |
//+------------------------------------------------------------------+
void SeedLadder()
  {
   double ask    = MarketInfo(Symbol(), MODE_ASK);
   double step   = StepPoints * g_point;
   double minStop = MarketInfo(Symbol(), MODE_STOPLEVEL) * g_point;

   datetime expiry = 0;
   if(PendingExpiryMin > 0)
      expiry = TimeCurrent() + (int)(PendingExpiryMin * 60);

   // Buy stops ABOVE current price (level 1 nearest).
   for(int i = 1; i <= LevelsAbove; i++)
     {
      double dist = step * i;
      if(dist < minStop) dist = minStop + step; // keep legal distance
      double price = NormalizeDouble(ask + dist, g_digits);
      double lots  = NormalizeLots(BaseLots * MathPow(LotMultiplier, i - 1));
      PlacePending(OP_BUYSTOP, price, lots, expiry);
     }

   // Buy limits BELOW current price (level 1 nearest).
   for(int j = 1; j <= LevelsBelow; j++)
     {
      double dist2 = step * j;
      if(dist2 < minStop) dist2 = minStop + step;
      double price2 = NormalizeDouble(ask - dist2, g_digits);
      double lots2  = NormalizeLots(BaseLots * MathPow(LotMultiplier, j - 1));
      PlacePending(OP_BUYLIMIT, price2, lots2, expiry);
     }
  }

//+------------------------------------------------------------------+
void PlacePending(int type, double price, double lots, datetime expiry)
  {
   double sl = 0.0;
   if(PerOrderSLPoints > 0)
      sl = NormalizeDouble(price - PerOrderSLPoints * g_point, g_digits); // buy-side SL below

   for(int attempt = 0; attempt < 3; attempt++)
     {
      int ticket = OrderSend(Symbol(), type, lots, price, SlippagePoints,
                             sl, 0, "PendingLadderEA", MagicNumber, expiry, clrDodgerBlue);
      if(ticket >= 0)
        {
         Print("Placed ", (type == OP_BUYSTOP ? "BUY STOP " : "BUY LIMIT "),
               DoubleToString(lots, 2), " @ ", DoubleToString(price, g_digits));
         return;
        }
      int err = GetLastError();
      Print("Pending OrderSend failed err=", err, " type=", type,
            " price=", DoubleToString(price, g_digits), " attempt=", attempt + 1);
      if(err == 134 || err == 148 || err == 130 /*invalid stops*/) return;
      Sleep(300);
      RefreshRates();
     }
  }
//+------------------------------------------------------------------+
