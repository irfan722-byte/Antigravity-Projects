"use client";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { clearTokens, isLoggedIn } from "@/lib/auth";
import type { Me, UserSettings } from "@/lib/types";

interface ProviderSummary { name: string; is_mock: boolean; disabled: boolean }
interface Ctx { me: Me | null; settings: UserSettings | null; loading: boolean; demo: boolean; dataNotice: string | null; reload: () => Promise<void>; logout: () => void; theme: string; setTheme: (t: string) => void }
const AppCtx = createContext<Ctx>({ me: null, settings: null, loading: true, demo: true, dataNotice: null, reload: async () => {}, logout: () => {}, theme: "system", setTheme: () => {} });
const KIND_LABEL: Record<string, string> = { economic_calendar: "economic calendar", trading_calendar: "trading calendar", macro_series: "macro series", news: "news", positioning: "positioning", etf_flows: "ETF flows" };
/** Text for the amber banner when prices are live but other inputs are synthetic or switched off. */
export function liveDataNotice(providers: Record<string, ProviderSummary> | undefined): string | null {
  if (!providers || !providers.market_data || providers.market_data.is_mock) return null;
  const synthetic = Object.entries(providers).filter(([k, p]) => k !== "market_data" && k !== "push" && p.is_mock).map(([k]) => KIND_LABEL[k] ?? k);
  const disabled = Object.entries(providers).filter(([k, p]) => k !== "market_data" && k !== "push" && p.disabled).map(([k]) => KIND_LABEL[k] ?? k);
  const parts = [`LIVE PRICES via ${providers.market_data.name}`];
  if (synthetic.length) parts.push(`synthetic: ${synthetic.join(", ")}`);
  if (disabled.length) parts.push(`disabled: ${disabled.join(", ")}`);
  parts.push("paper trading only, live execution disabled");
  return parts.join(" · ");
}

export function useApp() { return useContext(AppCtx); }

export function Providers({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(true);
  const [dataNotice, setDataNotice] = useState<string | null>(null);
  const [theme, setThemeState] = useState<string>("system");

  const applyTheme = useCallback((t: string) => {
    const dark = t === "dark" || (t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const meta = await api<{ demo_data: boolean; providers?: Record<string, ProviderSummary> }>("/api/meta", { auth: false });
      setDemo(meta.demo_data);
      setDataNotice(liveDataNotice(meta.providers));
    } catch { /* backend unreachable: keep demo=true so the banner stays visible */ }
    if (!isLoggedIn()) { setMe(null); setSettings(null); setLoading(false); return; }
    try {
      const m = await api<Me>("/api/auth/me");
      setMe(m);
      const s = await api<UserSettings>("/api/users/settings");
      setSettings(s);
      setThemeState(s.theme ?? "system");
      applyTheme(s.theme ?? "system");
      document.documentElement.lang = s.locale ?? "en";
      document.documentElement.dir = s.locale === "ar" ? "rtl" : "ltr";
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) { clearTokens(); setMe(null); }
    } finally { setLoading(false); }
  }, [applyTheme]);

  useEffect(() => { const t = localStorage.getItem("ag_theme") ?? "system"; setThemeState(t); applyTheme(t); void reload(); }, [reload, applyTheme]);
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);

  const value = useMemo<Ctx>(() => ({
    me, settings, loading, demo, dataNotice, reload,
    logout: () => { clearTokens(); setMe(null); setSettings(null); window.location.href = "/login"; },
    theme, setTheme: (t) => { setThemeState(t); localStorage.setItem("ag_theme", t); applyTheme(t); },
  }), [me, settings, loading, demo, dataNotice, reload, theme, applyTheme]);
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApi<T>(path: string | null, intervalMs = 0, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((x) => x + 1), []);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    const run = () => api<T>(path).then((d) => { if (alive) { setData(d); setError(null); } }).catch((e) => { if (alive) setError(e instanceof Error ? e.message : String(e)); }).finally(() => { if (alive) setLoading(false); });
    void run();
    const id = intervalMs > 0 ? setInterval(run, intervalMs) : undefined;
    return () => { alive = false; if (id) clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, intervalMs, tick, ...deps]);
  return { data, error, loading, refresh };
}
