//+------------------------------------------------------------------+
//|                                        NonRepaintChannel.mq4      |
//|   ATR channel + rejection dots  (genuinely non-repainting)       |
//|                                                                  |
//|   Reproduces the "red band / green band + red & green dots"      |
//|   look from the reference video, but built so that any dot,      |
//|   once printed on a CLOSED bar, never moves or disappears.       |
//+------------------------------------------------------------------+
#property copyright "Non-repaint reproduction"
#property link      ""
#property version   "1.00"
#property strict

#property indicator_chart_window
#property indicator_buffers 6

//--- band lines
#property indicator_color1 clrOrangeRed     // upper outer
#property indicator_color2 clrOrangeRed     // upper inner
#property indicator_color3 clrLimeGreen     // lower inner
#property indicator_color4 clrLimeGreen     // lower outer
#property indicator_width1 1
#property indicator_width2 1
#property indicator_width3 1
#property indicator_width4 1

//--- signal dots
#property indicator_color5 clrRed           // sell dot (top)
#property indicator_color6 clrLime          // buy dot (bottom)
#property indicator_width5 2
#property indicator_width6 2

//------------------------------------------------------------------
input int    MA_Period    = 34;    // basis EMA period
input int    ATR_Period   = 14;    // ATR period for channel width
input double Mult_Inner   = 1.5;   // inner band ATR multiplier
input double Mult_Outer   = 2.5;   // outer band ATR multiplier
input double DotOffsetPts  = 12;   // dot offset from candle (points)
//------------------------------------------------------------------

double UpOuter[], UpInner[], LoInner[], LoOuter[];
double SellDot[], BuyDot[];

//+------------------------------------------------------------------+
int OnInit()
  {
   SetIndexBuffer(0, UpOuter);  SetIndexStyle(0, DRAW_LINE);
   SetIndexBuffer(1, UpInner);  SetIndexStyle(1, DRAW_LINE);
   SetIndexBuffer(2, LoInner);  SetIndexStyle(2, DRAW_LINE);
   SetIndexBuffer(3, LoOuter);  SetIndexStyle(3, DRAW_LINE);

   SetIndexBuffer(4, SellDot);  SetIndexStyle(4, DRAW_ARROW); SetIndexArrow(4, 159); // dot
   SetIndexBuffer(5, BuyDot);   SetIndexStyle(5, DRAW_ARROW);  SetIndexArrow(5, 159); // dot

   IndicatorShortName("NonRepaintChannel(" + (string)MA_Period + "," + (string)ATR_Period + ")");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Non-repaint rule:                                                |
//|  * Bands are plotted on every bar (they follow price and that    |
//|    is expected/allowed).                                         |
//|  * Dots are computed ONLY on already-closed bars (shift >= 1)    |
//|    using data strictly to the LEFT of the signal bar. The dot    |
//|    depends only on bars that are already final, so it can never  |
//|    be redrawn on a later tick -> no repaint, no back-painting.   |
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   int need = MathMax(MA_Period, ATR_Period) + 3;
   if(rates_total < need) return(0);

   // recompute only the un-finalised tail; leave older bars untouched
   int limit = rates_total - prev_calculated;
   if(prev_calculated == 0) limit = rates_total - need;
   if(limit > rates_total - 2) limit = rates_total - 2;

   double point = _Point;

   for(int i = limit; i >= 1; i--)   // note: i starts at 1, bar 0 (forming) is never signalled
     {
      double basis = iMA(NULL, 0, MA_Period, 0, MODE_EMA, PRICE_CLOSE, i);
      double atr   = iATR(NULL, 0, ATR_Period, i);

      UpInner[i] = basis + Mult_Inner * atr;
      UpOuter[i] = basis + Mult_Outer * atr;
      LoInner[i] = basis - Mult_Inner * atr;
      LoOuter[i] = basis - Mult_Outer * atr;

      SellDot[i] = EMPTY_VALUE;
      BuyDot[i]  = EMPTY_VALUE;

      // --- rejection signals on the CLOSED bar i (uses only bars i, i+1 = past) ---
      // Sell: this bar poked above the inner upper band but closed back below it
      if(high[i] > UpInner[i] && close[i] < UpInner[i] && close[i] < open[i])
         SellDot[i] = high[i] + DotOffsetPts * point;

      // Buy: this bar poked below the inner lower band but closed back above it
      if(low[i] < LoInner[i] && close[i] > LoInner[i] && close[i] > open[i])
         BuyDot[i] = low[i] - DotOffsetPts * point;
     }

   return(rates_total);
  }
//+------------------------------------------------------------------+
