"use client";
/**
 * Readable rendering for structured API payloads.
 *
 * Objects become label/value tables, arrays of records become tables with one column
 * per field, timestamps are shown in the user's timezone and numbers are formatted.
 * Nothing on a page should fall back to a raw JSON dump; use <DataView> (or the
 * inline `summarize()` for table cells) instead.
 */
import React from "react";
import { fmtNum, fmtTime } from "@/lib/format";
import { useApp } from "./Providers";

const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/;
const MAX_ROWS = 50;
const MAX_COLS = 12;
/** Nested blocks bigger than this start collapsed so long payloads stay scannable. */
const COLLAPSE_AFTER = 6;

type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => typeof v === "object" && v !== null && !Array.isArray(v);
const isScalar = (v: unknown): boolean => !isRec(v) && !Array.isArray(v);

/** snake_case / camelCase key -> words. Tokens in capitals or with digits (M5, OOS, R) are kept as they are. */
export function label(key: string): string {
  const words = key.replace(/_/g, " ").replace(/([a-z0-9])([A-Z])/g, "$1 $2").trim().split(/\s+/);
  return words.map((w, i) => (w === w.toUpperCase() || /\d/.test(w) ? w : i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w)).join(" ");
}

export function fmtAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "–";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

export function formatScalar(v: unknown, tz = "UTC"): string {
  if (v === null || v === undefined || v === "") return "–";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : fmtNum(v, Math.abs(v) < 1 ? 4 : 2);
  if (typeof v === "string") return ISO.test(v) ? fmtTime(v, tz) : v;
  return String(v);
}

/** One-line text form for table cells and status lines. */
export function summarize(v: unknown, tz = "UTC", max = 160): string {
  let s: string;
  if (isRec(v)) s = Object.entries(v).map(([k, x]) => `${label(k)}: ${isScalar(x) ? formatScalar(x, tz) : summarize(x, tz, 48)}`).join("; ");
  else if (Array.isArray(v)) s = v.length ? v.map((x) => (isScalar(x) ? formatScalar(x, tz) : summarize(x, tz, 48))).join(", ") : "none";
  else s = formatScalar(v, tz);
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

function columnsOf(rows: Rec[]): string[] {
  const cols: string[] = [];
  for (const r of rows) for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k);
  return cols.slice(0, MAX_COLS);
}

function Node({ value, tz, depth }: { value: unknown; tz: string; depth: number }) {
  if (isScalar(value)) return <span>{formatScalar(value, tz)}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="muted">none</span>;
    if (value.every(isScalar)) return value.length > 8 ? <ul className="list-disc ps-5">{value.map((x, i) => <li key={i}>{formatScalar(x, tz)}</li>)}</ul> : <span>{value.map((x) => formatScalar(x, tz)).join(", ")}</span>;
    if (value.every(isRec)) {
      const rows = value as Rec[];
      const cols = columnsOf(rows);
      const shown = rows.slice(0, MAX_ROWS);
      const table = (
        <div className="scroll-x">
          <table className="table data-table"><thead><tr>{cols.map((c) => <th key={c}>{label(c)}</th>)}</tr></thead>
            <tbody>{shown.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c}><Node value={r[c]} tz={tz} depth={depth + 1} /></td>)}</tr>)}</tbody></table>
          {rows.length > MAX_ROWS ? <p className="data-note">Showing {MAX_ROWS} of {rows.length} rows.</p> : null}
        </div>
      );
      return depth > 0 && rows.length > COLLAPSE_AFTER ? <details><summary className="text-sm">{rows.length} rows</summary>{table}</details> : table;
    }
    if (value.every(Array.isArray)) {
      const rows = value as unknown[][];
      const shown = rows.slice(0, MAX_ROWS);
      return (
        <div className="scroll-x">
          <table className="table data-table"><tbody>{shown.map((r, i) => <tr key={i}>{r.map((x, j) => <td key={j}><Node value={x} tz={tz} depth={depth + 1} /></td>)}</tr>)}</tbody></table>
          {rows.length > MAX_ROWS ? <p className="data-note">Showing {MAX_ROWS} of {rows.length} rows.</p> : null}
        </div>
      );
    }
    return <ul className="list-disc ps-5">{value.map((x, i) => <li key={i}><Node value={x} tz={tz} depth={depth + 1} /></li>)}</ul>;
  }
  const entries = Object.entries(value as Rec);
  if (!entries.length) return <span className="muted">none</span>;
  const table = (
    <table className="table kv"><tbody>
      {entries.map(([k, x]) => <tr key={k}><th scope="row">{label(k)}</th><td><Node value={x} tz={tz} depth={depth + 1} /></td></tr>)}
    </tbody></table>
  );
  return depth > 0 && entries.length > COLLAPSE_AFTER ? <details><summary className="text-sm">{entries.length} fields</summary>{table}</details> : table;
}

export function DataView({ value, tz }: { value: unknown; tz?: string }) {
  const { settings } = useApp();
  const zone = tz ?? settings?.timezone ?? "UTC";
  if (value === undefined || value === null) return <p className="muted text-sm">None</p>;
  return <div className="data-view text-sm"><Node value={value} tz={zone} depth={0} /></div>;
}
