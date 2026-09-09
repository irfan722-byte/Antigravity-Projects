const ACCESS = "ag_access";
const REFRESH = "ag_refresh";

export function getAccess(): string | null {
  try { return localStorage.getItem(ACCESS); } catch { return null; }
}
export function getRefresh(): string | null {
  try { return localStorage.getItem(REFRESH); } catch { return null; }
}
export function setTokens(access: string, refresh: string): void {
  try { localStorage.setItem(ACCESS, access); localStorage.setItem(REFRESH, refresh); } catch { /* storage unavailable */ }
}
export function clearTokens(): void {
  try { localStorage.removeItem(ACCESS); localStorage.removeItem(REFRESH); } catch { /* ignore */ }
}
export function isLoggedIn(): boolean { return !!getAccess(); }
