//+------------------------------------------------------------------+
//|                                        NonRepaintChannel.mq4      |
//|   ATR channel + CONFIRMED trend-flip dots (non-repainting)       |
//|                                                                  |
//|   Reproduces the reference video: red band above, green band     |
//|   below, and a few red/green dots at major turns.                |
//|                                                                  |
//|   Signals are NOT band-touch rejections (those give noise).      |
//|   They are SuperTrend-style trend flips: a dot prints only when  |
//|   price CLOSES through the trailing ATR band and the trend       |
//|   direction changes. That close-through-band IS the             |
//|   confirmation, so signals are rare, clean and alternating.      |
//+------------------------------------------------------------------+
#property copyright "Non-repaint reproduction"
#property link      ""
#property version   "3.00"
#property strict

#property indicator_chart_window
#property indicator_buffers 6

//--- band lines (visual channel, like the video)
#property indicator_color1 clrOrangeRed     // upper outer
#property indicator_color2 clrOrangeRed     // upper inner
#property indicator_color3 clrLimeGreen     // lower inner
#property indicator_color4 clrLimeGreen     // lower outer
#property indicator_width1 2
#property indicator_width2 1
#property indicator_width3 1
#property indicator_width4 2

//--- signal dots
#property indicator_color5 clrRed           // sell dot (top)  -> trend flips DOWN
#property indicator_color6 clrLime          // buy dot (bottom) -> trend flips UP
#property indicator_width5 3
#property indicator_width6 3

//------------------------------------------------------------------
//--- visual channel (envelope) ---
input int    MA_Period      = 60;    // basis EMA period for the drawn channel
input int    Smooth         = 5;     // extra smoothing of the drawn bands (1 = off)
input int    ATR_Period     = 30;    // ATR period for the drawn channel width
input double Mult_Inner     = 1.6;   // inner band ATR multiplier
input double Mult_Outer     = 2.6;   // outer band ATR multiplier

//--- confirmed signal engine (SuperTrend) ---
input int    ST_ATR_Period  = 22;    // ATR period for the trend engine
input double ST_Mult        = 3.5;   // trend sensitivity: HIGHER = fewer, later, more confirmed
input double DotOffsetPts   = 25;    // dot offset from candle (points)
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

   SetIndexBuffer(4, SellDot);  SetIndexStyle(4, DRAW_ARROW); SetIndexArrow(4, 159);
   SetIndexBuffer(5, BuyDot);   SetIndexStyle(5, DRAW_ARROW);  SetIndexArrow(5, 159);

   IndicatorShortName("NonRepaintChannel(ST " + (string)ST_ATR_Period + "x" + DoubleToString(ST_Mult,1) + ")");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Why this is non-repaint:                                         |
//|  * SuperTrend is computed forward (oldest -> newest). The trend  |
//|    on bar i depends only on bar i's close and the band carried   |
//|    from bar i+1 (the PAST). No future bar is used.               |
//|  * A flip is detected only on CLOSED bars (i >= 1); the forming  |
//|    bar 0 is never signalled.                                     |
//|  * Once bar i has closed its close is final, so the flip and its |
//|    dot are fixed forever -> the dot cannot move or vanish.       |
//|  The trade-off: the dot appears at the CLOSE of the flip bar     |
//|  (one bar of confirmation). That confirmation is exactly why it  |
//|  does not repaint and why it does not fire on every wick.        |
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
   int need = MathMax(MathMax(MA_Period, ATR_Period), ST_ATR_Period) + Smooth + 5;
   if(rates_total < need) return(0);

   // ================= 1) drawn channel (envelope) =================
   for(int i = rates_total - 2; i >= 0; i--)
     {
      double basis = iMA(NULL, 0, MA_Period, 0, MODE_EMA, PRICE_CLOSE, i);
      double atr   = iATR(NULL, 0, ATR_Period, i);
      UpInner[i] = basis + Mult_Inner * atr;
      UpOuter[i] = basis + Mult_Outer * atr;
      LoInner[i] = basis - Mult_Inner * atr;
      LoOuter[i] = basis - Mult_Outer * atr;
     }
   if(Smooth > 1)
     {
      SmoothBuffer(UpInner, rates_total, Smooth);
      SmoothBuffer(UpOuter, rates_total, Smooth);
      SmoothBuffer(LoInner, rates_total, Smooth);
      SmoothBuffer(LoOuter, rates_total, Smooth);
     }

   // ================= 2) SuperTrend confirmed signals =============
   // Series arrays: index 0 = newest, higher index = older.
   // "previous bar" (the past) is i+1. Build forward: oldest -> newest.
   static double finalUp[], finalLo[];
   static int    trend[];
   ArrayResize(finalUp, rates_total);
   ArrayResize(finalLo, rates_total);
   ArrayResize(trend,   rates_total);

   int start = rates_total - need;      // first bar we can compute
   if(start < 1) start = 1;

   // seed the oldest computed bar
   {
      int i = start;
      double atr = iATR(NULL, 0, ST_ATR_Period, i);
      double mid = (high[i] + low[i]) / 2.0;
      finalUp[i] = mid + ST_Mult * atr;
      finalLo[i] = mid - ST_Mult * atr;
      trend[i]   = 1;                   // assume up to start
      SellDot[i] = EMPTY_VALUE;
      BuyDot[i]  = EMPTY_VALUE;
   }

   for(int i = start - 1; i >= 1; i--)  // i decreasing = moving to newer bars
     {
      SellDot[i] = EMPTY_VALUE;
      BuyDot[i]  = EMPTY_VALUE;

      double atr = iATR(NULL, 0, ST_ATR_Period, i);
      double mid = (high[i] + low[i]) / 2.0;
      double basicUp = mid + ST_Mult * atr;
      double basicLo = mid - ST_Mult * atr;

      int p = i + 1;                    // previous (older) bar = the past

      // trailing bands (only tighten in the trend direction)
      finalUp[i] = (basicUp < finalUp[p] || close[p] > finalUp[p]) ? basicUp : finalUp[p];
      finalLo[i] = (basicLo > finalLo[p] || close[p] < finalLo[p]) ? basicLo : finalLo[p];

      // trend state
      if(trend[p] == 1)                 // was up: flip down only on close below lower band
         trend[i] = (close[i] < finalLo[p]) ? -1 : 1;
      else                              // was down: flip up only on close above upper band
         trend[i] = (close[i] > finalUp[p]) ?  1 : -1;

      // dot exactly on the bar where trend changed (confirmed at this bar's close)
      if(trend[i] == 1 && trend[p] == -1)
         BuyDot[i]  = low[i]  - DotOffsetPts * _Point;   // green, near the bottom
      else if(trend[i] == -1 && trend[p] == 1)
         SellDot[i] = high[i] + DotOffsetPts * _Point;   // red, near the top
     }

   return(rates_total);
  }

//+------------------------------------------------------------------+
//| simple SMA smoothing of a series buffer (index 0 = newest)       |
//+------------------------------------------------------------------+
void SmoothBuffer(double &buf[], int total, int period)
  {
   if(period <= 1) return;
   static double tmp[];
   ArrayResize(tmp, total);
   for(int i = 0; i < total; i++) tmp[i] = buf[i];
   for(int i = total - 1; i >= 0; i--)
     {
      double sum = 0; int cnt = 0;
      for(int k = 0; k < period; k++)
        {
         int idx = i + k;
         if(idx >= total) break;
         if(tmp[idx] == EMPTY_VALUE) break;
         sum += tmp[idx]; cnt++;
        }
      buf[i] = (cnt > 0) ? sum / cnt : tmp[i];
     }
  }
//+------------------------------------------------------------------+
