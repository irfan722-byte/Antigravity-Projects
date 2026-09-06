"use client";
import { useState } from "react";
import { useApp, useApi } from "@/components/Providers";
import { DecisionCard, ErrorBox, Loading } from "@/components/ui";
import type { Decision } from "@/lib/types";

const STATUSES = ["", "BUY_SETUP", "SELL_SETUP", "WAIT", "NO_TRADE", "EVENT_LOCKOUT", "DATA_UNAVAILABLE"];
const HORIZONS = ["", "SCALP", "INTRADAY", "SWING", "WEEKLY"];

export default function Signals() {
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const [status, setStatus] = useState(""); const [horizon, setHorizon] = useState("");
  const qs = new URLSearchParams({ limit: "60", ...(status ? { status } : {}), ...(horizon ? { horizon } : {}) }).toString();
  const { data, error } = useApi<{ items: Decision[] }>(`/api/decisions/feed?${qs}`, 30000, [qs]);
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Signal feed</h1>
      <div className="flex gap-2 mb-3 flex-wrap">
        <label className="text-sm">Status <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>{STATUSES.map((s) => <option key={s} value={s}>{s || "all"}</option>)}</select></label>
        <label className="text-sm">Horizon <select className="input w-auto" value={horizon} onChange={(e) => setHorizon(e.target.value)}>{HORIZONS.map((s) => <option key={s} value={s}>{s || "all"}</option>)}</select></label>
      </div>
      <ErrorBox error={error} />
      {!data ? <Loading /> : data.items.length ? <div className="space-y-3">{data.items.map((d) => <DecisionCard key={d.decision_id} d={d} tz={tz} />)}</div> : <p className="muted">No decisions recorded yet. The analysis loop records a decision when a status changes and at least every 15 minutes.</p>}
    </div>
  );
}
