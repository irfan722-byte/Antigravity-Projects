"use client";
import React from "react";
import Link from "next/link";
import { fmtNum, fmtTime, statusLabel } from "@/lib/format";
import type { Decision, Gate, EvidenceItem } from "@/lib/types";

export function StatusBadge({ status }: { status: string }) {
  const icon: Record<string, string> = { BUY_SETUP: "▲", SELL_SETUP: "▼", WAIT: "◔", NO_TRADE: "■", EVENT_LOCKOUT: "⏸", DATA_UNAVAILABLE: "⚠" };
  return <span className={`badge status-${status}`} role="status"><span aria-hidden>{icon[status] ?? "•"}</span>{statusLabel(status)}</span>;
}

export function Kpi({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return <div className="kpi card"><span className="label">{label}</span><span className="value">{value}</span>{sub ? <span className="muted text-xs">{sub}</span> : null}</div>;
}

export function Section({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return <section className="card mb-4" aria-labelledby={title.replace(/\s+/g, "-")}><div className="flex items-center justify-between mb-2"><h2 id={title.replace(/\s+/g, "-")} className="font-bold text-base">{title}</h2>{right}</div>{children}</section>;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div role="alert" className="card mb-3" style={{ borderColor: "var(--sell)" }}>{error}</div>;
}

export function Loading({ label = "Loading" }: { label?: string }) { return <p className="muted" aria-live="polite">{label}…</p>; }

export function DecisionCard({ d, tz, compact = false }: { d: Decision | null; tz: string; compact?: boolean }) {
  if (!d) return <div className="card"><p className="muted">No evaluation yet.</p></div>;
  const s = d.setup;
  return (
    <article className="card" aria-label={`${d.horizon} decision ${d.status}`}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2"><strong>{d.horizon}</strong><StatusBadge status={d.status} /></div>
        <span className="muted text-xs">{fmtTime(d.as_of, tz)}</span>
      </div>
      {s ? (
        <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
          <div><span className="muted">Entry zone</span><br />{fmtNum(s.entry_zone_low)} – {fmtNum(s.entry_zone_high)}</div>
          <div><span className="muted">Stop</span><br />{fmtNum(s.stop_loss)}</div>
          {s.targets.slice(0, 2).map((t) => <div key={t.label}><span className="muted">{t.label}</span><br />{fmtNum(t.price)} <span className="muted">R {fmtNum(t.net_reward_to_risk)}</span></div>)}
          <div><span className="muted">Expires</span><br />{fmtTime(s.expiry, tz)}</div>
          <div><span className="muted">Size</span><br />{String((s.position_size as { lots?: number }).lots ?? "n/a")} lots · {fmtNum(s.total_account_risk_usd)} USD</div>
          <div><span className="muted">Confidence</span><br />{Math.round(s.confidence_low * 100)}–{Math.round(s.confidence_high * 100)}% (n={s.historical_sample_size})</div>
          <div><span className="muted">Strategy</span><br />{s.strategy_id} v{s.strategy_version}</div>
        </div>
      ) : null}
      {!compact && <p className="mt-2 text-sm">{d.reason}</p>}
      {s?.conflicting_horizons?.length ? <p className="text-sm mt-1" style={{ color: "var(--sell)" }}>Conflicting direction on: {s.conflicting_horizons.join(", ")}</p> : null}
      <div className="mt-2 flex gap-3 text-sm"><Link href={`/setups/${d.decision_id}`}>Setup details</Link><Link href={`/evidence/${d.decision_id}`}>Evidence Inspector</Link></div>
    </article>
  );
}

export function GateList({ gates }: { gates: Gate[] }) {
  if (!gates?.length) return <p className="muted">None</p>;
  return <ul className="text-sm space-y-1">{gates.map((g) => <li key={g.code}><span aria-hidden>{g.passed ? "✓" : "✗"}</span> <span className="sr-only">{g.passed ? "passed" : "failed"}</span> <strong>{g.code}</strong> {g.name}: <span className="muted">{g.reason}</span></li>)}</ul>;
}

export function EvidenceList({ items }: { items: EvidenceItem[] }) {
  if (!items?.length) return <p className="muted">None recorded</p>;
  return <ul className="text-sm space-y-1">{items.map((e, i) => <li key={`${e.key}-${i}`}><strong>{e.family}</strong> · {e.key} {e.direction > 0 ? "▲" : e.direction < 0 ? "▼" : "•"} {Math.round(e.strength * 100)}% — {e.description} <span className="muted">[{e.source}]</span></li>)}</ul>;
}

export function Json({ value }: { value: unknown }) { return <pre className="code">{JSON.stringify(value, null, 2)}</pre>; }
