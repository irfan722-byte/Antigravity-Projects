"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useApp, useApi } from "./Providers";
import { t } from "@/lib/i18n";
import { fmtNum, fmtTime } from "@/lib/format";
import type { Quote } from "@/lib/types";

const NAV: { href: string; key: string; group: string; admin?: boolean }[] = [
  { href: "/dashboard", key: "dashboard", group: "Trade" }, { href: "/signals", key: "signals", group: "Trade" }, { href: "/charts", key: "charts", group: "Trade" }, { href: "/paper", key: "paper", group: "Trade" }, { href: "/journal", key: "journal", group: "Trade" },
  { href: "/calendar", key: "calendar", group: "Context" }, { href: "/regime", key: "regime", group: "Context" }, { href: "/intermarket", key: "intermarket", group: "Context" },
  { href: "/risk", key: "risk", group: "Risk" }, { href: "/calculator", key: "calculator", group: "Risk" },
  { href: "/strategies", key: "strategies", group: "Research" }, { href: "/backtest", key: "backtest", group: "Research" }, { href: "/performance", key: "performance", group: "Research" }, { href: "/calibration", key: "calibration", group: "Research" },
  { href: "/notifications", key: "notifications", group: "System" }, { href: "/data-health", key: "health", group: "System" }, { href: "/settings", key: "settings", group: "System" }, { href: "/privacy", key: "privacy", group: "System" }, { href: "/audit", key: "audit", group: "System" }, { href: "/admin", key: "admin", group: "System", admin: true },
];
const MOBILE = ["/dashboard", "/signals", "/charts", "/paper", "/notifications"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { me, settings, loading, demo, dataNotice, logout, theme, setTheme } = useApp();
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { data: q } = useApi<Quote>(me ? "/api/market/quote" : null, 15000);
  useEffect(() => {
    if (loading) return;
    if (!me) router.replace(`/login?next=${encodeURIComponent(path)}`);
    else if (!me.onboarding_completed && path !== "/onboarding") router.replace("/onboarding");
  }, [me, loading, path, router]);
  if (loading || !me) return <main className="p-6"><p className="muted">Loading…</p></main>;
  const tz = settings?.timezone ?? "UTC";
  const groups = Array.from(new Set(NAV.map((n) => n.group)));
  return (
    <div className="min-h-screen flex flex-col">
      {demo ? <div className="demo-banner" role="alert">{t("demo_banner")}</div> : dataNotice ? <div className="live-banner" role="status">{dataNotice}</div> : null}
      <header className="flex items-center gap-3 px-3 py-2 border-b" style={{ borderColor: "var(--border)" }}>
        <button className="btn sm:hidden" aria-label="Open navigation" aria-expanded={open} onClick={() => setOpen(!open)}>☰</button>
        <Link href="/dashboard" className="font-extrabold" style={{ color: "var(--accent)" }}>AurumGuard</Link>
        <div className="ms-auto flex items-center gap-3 text-sm" aria-live="polite">
          {q ? <span title={`Data ${fmtTime(q.ts, tz)} via ${q.provider}`}><strong>XAU/USD</strong> {fmtNum(q.bid)} / {fmtNum(q.ask)} <span className="muted">spr {fmtNum(q.spread)} · {q.session}</span></span> : <span className="muted">quote…</span>}
          <select aria-label="Theme" className="input w-auto py-1" value={theme} onChange={(e) => setTheme(e.target.value)}><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select>
          <button className="btn py-1" onClick={logout}>Log out</button>
        </div>
      </header>
      <div className="flex flex-1">
        <nav aria-label="Main" className={`${open ? "block" : "hidden"} sm:block w-56 shrink-0 border-e p-3 text-sm`} style={{ borderColor: "var(--border)" }}>
          {groups.map((g) => (
            <div key={g} className="mb-3"><div className="muted text-xs uppercase mb-1">{g}</div>
              {NAV.filter((n) => n.group === g && (!n.admin || me.role === "admin")).map((n) => <Link key={n.href} href={n.href} aria-current={path === n.href ? "page" : undefined} className={`block rounded px-2 py-1 ${path === n.href ? "font-bold" : ""}`} style={path === n.href ? { background: "var(--bg)" } : {}} onClick={() => setOpen(false)}>{t(n.key)}</Link>)}
            </div>
          ))}
        </nav>
        <main className="flex-1 p-3 sm:p-5 pb-20 sm:pb-5 max-w-6xl">{children}</main>
      </div>
      <nav aria-label="Quick" className="sm:hidden fixed bottom-0 inset-x-0 flex justify-around border-t py-2 text-xs" style={{ background: "var(--card)", borderColor: "var(--border)" }}>
        {MOBILE.map((h) => { const n = NAV.find((x) => x.href === h)!; return <Link key={h} href={h} aria-current={path === h ? "page" : undefined} className={path === h ? "font-bold" : ""}>{t(n.key)}</Link>; })}
      </nav>
      <footer className="px-4 py-2 text-xs muted border-t" style={{ borderColor: "var(--border)" }}>{t("uncertain")} No regulatory approval is claimed. Live order execution is disabled.</footer>
    </div>
  );
}
