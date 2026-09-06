"use client";
import React, { useEffect, useRef } from "react";
import { CandlestickSeries, ColorType, createChart, LineSeries, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import type { Candle } from "@/lib/types";

export interface Level { price: number; label: string; color?: string }

export function CandleChart({ candles, levels = [], height = 380, dark = false }: { candles: Candle[]; levels?: Level[]; height?: number; dark?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, { height, layout: { background: { type: ColorType.Solid, color: dark ? "#121821" : "#ffffff" }, textColor: dark ? "#e8eaee" : "#15181d" }, grid: { vertLines: { color: dark ? "#253041" : "#eee" }, horzLines: { color: dark ? "#253041" : "#eee" } }, timeScale: { timeVisible: true, secondsVisible: false }, autoSize: true });
    chartRef.current = chart;
    const series = chart.addSeries(CandlestickSeries, { upColor: "#1b7f4b", downColor: "#b3261e", borderVisible: false, wickUpColor: "#1b7f4b", wickDownColor: "#b3261e" });
    series.setData(candles.map((c) => ({ time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close })));
    for (const l of levels) {
      series.createPriceLine({ price: l.price, color: l.color ?? "#9a6b00", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: l.label });
    }
    if (candles.length > 60) {
      const ema = chart.addSeries(LineSeries, { color: "#6b4bb3", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      const k = 2 / 21; let e = candles[0].close; const pts = candles.map((c) => { e = c.close * k + e * (1 - k); return { time: c.time as UTCTimestamp, value: e }; });
      ema.setData(pts.slice(20));
    }
    chart.timeScale().fitContent();
    return () => { chart.remove(); chartRef.current = null; };
  }, [candles, levels, height, dark]);
  return <div ref={ref} role="img" aria-label={`Candlestick chart with ${candles.length} bars`} style={{ width: "100%", height }} />;
}
