"use client";
import Link from "next/link";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Loading, Section } from "@/components/ui";
import { countdown, fmtTime } from "@/lib/format";
import type { CalendarEvent } from "@/lib/types";

export default function Calendar() {
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data, error } = useApi<{ events: CalendarEvent[]; provider: string; demo_data: boolean }>("/api/calendar?days_back=7&days_ahead=21", 60000);
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Economic calendar (USD)</h1>
      <ErrorBox error={error} />
      {data?.demo_data && <p className="demo-banner rounded mb-3">DEMO DATA — synthetic events and values</p>}
      <Section title="Events">
        {!data ? <Loading /> : <div className="scroll-x"><table className="table"><thead><tr><th>When ({tz})</th><th>In</th><th>Event</th><th>Imp.</th><th>Actual</th><th>Consensus</th><th>Prior</th><th>Rev. prior</th><th>Surprise (z)</th><th>Verified</th></tr></thead><tbody>
          {data.events.map((e) => <tr key={e.event_id}><td>{fmtTime(e.scheduled_ts, tz)}</td><td>{countdown(e.scheduled_ts)}</td><td><Link href={`/calendar/${e.event_id}`}>{e.name}</Link></td><td>{e.importance}</td><td>{e.actual ?? "–"}</td><td>{e.consensus ?? "–"}</td><td>{e.prior ?? "–"}</td><td>{e.revised_prior ?? "–"}</td><td>{e.surprise ?? "–"} {e.standardised_surprise !== null ? `(${e.standardised_surprise})` : ""}</td><td>{e.verification}</td></tr>)}
        </tbody></table></div>}
        <p className="muted text-xs mt-1">Source timezone America/New_York; shown in your timezone. Provider: {data?.provider}. Unreleased values are never shown or guessed.</p>
      </Section>
    </div>
  );
}
