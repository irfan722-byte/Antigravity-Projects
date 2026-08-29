//+------------------------------------------------------------------+
//|                                        NonRepaintChannel.mq4      |
//|   Smooth ATR channel + sparse, alternating reversal dots         |
//|   (genuinely non-repainting)                                     |
//|                                                                  |
//|   Reproduces the "red band / green band + a few red & green      |
//|   dots at major swings" look from the reference video.           |
//|                                                                  |
//|   Noise control: a dot only prints when the OUTER band is        |
//|   pierced AND the previous dot was of the opposite type          |
//|   (buy -> sell -> buy ...), plus a minimum-bar cooldown. This    |
//|   is what keeps signals rare and long-term instead of firing     |
//|   on every candle.                                               |
//+------------------------------------------------------------------+
#property copyright "Non-repaint reproduction"
#property link      ""
#property version   "2.00"
#property strict

#property indicator_chart_window
#property indicator_buffers 6

//--- band lines
#property indicator_color1 clrOrangeRed     // upper outer
#property indicator_color2 clrOrangeRed     // upper inner
#property indicator_color3 clrLimeGreen     // lower inner
#property indicator_color4 clrLimeGreen     // lower outer
#property indicator_width1 2
#property indicator_width2 1
#property indicator_width3 1
#property indicator_width4 2

//--- signal dots
#property indicator_color5 clrRed           // sell dot (top)
#property indicator_color6 clrLime          // buy dot (bottom)
#property indicator_width5 3
#property indicator_width6 3

//------------------------------------------------------------------
input int    MA_Period      = 60;    // basis EMA period (bigger = smoother, fewer signals)
input int    Smooth         = 5;     // extra smoothing of the bands (1 = none)
input int    ATR_Period     = 30;    // ATR period for channel width
input double Mult_Inner     = 1.6;   // inner band ATR multiplier
input double Mult_Outer     = 2.6;   // outer band ATR multiplier (signal trigger)
input bool   Signal_On_Outer= true;  // true: trigger on outer band, false: inner band
input bool   Alternate      = true;  // enforce buy -> sell -> buy alternation
input int    MinBarsBetween = 15;    // min bars between two signals (cooldown)
input double DotOffsetPts   = 20;    // dot offset from candle (points)
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
//| Non-repaint design:                                              |
//|  * Every signal is decided on already-CLOSED bars (shift >= 1)   |
//|    using only data to the LEFT. No future bar is read.           |
//|  * The full history is recomputed deterministically each tick    |
//|    from the same fixed starting bar, so a dot that printed on a  |
//|    closed bar is identical on every later tick -> no repaint.    |
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
   int need = MathMax(MA_Period, ATR_Period) + Smooth + 5;
   if(rates_total < need) return(0);

   // --- 1) bands on every bar -------------------------------------
   // raw inner/outer first, then optionally smooth them.
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

   // --- 2) signals: full deterministic pass, oldest -> newest -----
   // state machine on CLOSED bars only (i >= 1).
   int    lastSide = 0;      // 0 none, +1 last was BUY, -1 last was SELL
   int    lastBar  = -100000;

   for(int i = rates_total - 2; i >= 1; i--)   // note: i>=1, forming bar 0 never signals
     {
      SellDot[i] = EMPTY_VALUE;
      BuyDot[i]  = EMPTY_VALUE;

      double upTrig = Signal_On_Outer ? UpOuter[i] : UpInner[i];
      double loTrig = Signal_On_Outer ? LoOuter[i] : LoInner[i];
      if(upTrig == EMPTY_VALUE || loTrig == EMPTY_VALUE) continue;

      bool cooled = (lastBar < 0) || (i_distance(i, lastBar) >= MinBarsBetween);

      // SELL: bar pokes above the trigger band and rejects (closes below it, down bar)
      bool sellRaw = (high[i] > upTrig && close[i] < upTrig && close[i] < open[i]);
      // BUY: bar pokes below the trigger band and rejects (closes above it, up bar)
      bool buyRaw  = (low[i]  < loTrig && close[i] > loTrig && close[i] > open[i]);

      if(sellRaw)
        {
         bool okAlt = (!Alternate) || (lastSide != -1); // don't repeat a sell
         if(okAlt && cooled)
           {
            SellDot[i] = high[i] + DotOffsetPts * _Point;
            lastSide = -1; lastBar = i;
            continue;
           }
        }
      if(buyRaw)
        {
         bool okAlt = (!Alternate) || (lastSide != 1);  // don't repeat a buy
         if(okAlt && cooled)
           {
            BuyDot[i] = low[i] - DotOffsetPts * _Point;
            lastSide = 1; lastBar = i;
           }
        }
     }

   return(rates_total);
  }

//+------------------------------------------------------------------+
//| distance in bars between two series indices                      |
//+------------------------------------------------------------------+
int i_distance(int a, int b) { return (int)MathAbs(a - b); }

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
