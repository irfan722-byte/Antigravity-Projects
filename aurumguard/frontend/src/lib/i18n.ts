// Minimal i18n scaffold. Add locales by extending the dictionary; RTL is driven by `dir()`.
const en: Record<string, string> = {
  dashboard: "Dashboard", signals: "Signal feed", charts: "Charts", calendar: "Economic calendar", regime: "Market regime", intermarket: "Intermarket", risk: "Risk", calculator: "Position size", paper: "Paper trading", journal: "Trade journal", backtest: "Backtesting lab", strategies: "Strategy registry", performance: "Performance", calibration: "Calibration", notifications: "Notifications", health: "Data health", settings: "Settings", privacy: "Privacy", audit: "Audit", admin: "Administration",
  demo_banner: "DEMO DATA - synthetic prices and events. Nothing here reflects the real market.",
  uncertain: "Every setup is uncertain. This is analysis, not advice.",
};
const ar: Record<string, string> = {}; // Arabic translation slot (architecture only in MVP)
const dicts: Record<string, Record<string, string>> = { en, ar };
export function t(key: string, locale = "en"): string { return dicts[locale]?.[key] ?? en[key] ?? key; }
export function dir(locale: string): "ltr" | "rtl" { return locale === "ar" ? "rtl" : "ltr"; }
