import { clearTokens, getAccess, getRefresh, setTokens } from "./auth";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

async function refresh(): Promise<boolean> {
  const rt = getRefresh();
  if (!rt) return false;
  const r = await fetch(`${BASE}/api/auth/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }) });
  if (!r.ok) { clearTokens(); return false; }
  const j = await r.json();
  setTokens(j.access_token, j.refresh_token);
  return true;
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown; auth?: boolean; retry?: boolean } = {}): Promise<T> {
  const { method = "GET", body, auth = true, retry = true } = opts;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) { const t = getAccess(); if (t) headers.Authorization = `Bearer ${t}`; }
  const res = await fetch(`${BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401 && auth && retry && (await refresh())) return api<T>(path, { ...opts, retry: false });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = (data && typeof data === "object" && "detail" in data) ? (data as { detail: unknown }).detail : data;
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}

export function streamUrl(): string { return `${BASE}/api/stream`; }
