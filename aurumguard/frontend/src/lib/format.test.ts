import { describe, expect, it } from "vitest";
import { countdown, fmtNum, fmtTime, statusLabel } from "./format";

describe("format", () => {
  it("formats numbers and n/a", () => { expect(fmtNum(2400.456)).toBe("2,400.46"); expect(fmtNum(null)).toBe("n/a"); });
  it("formats time in user timezone", () => { const s = fmtTime("2026-03-13T16:00:00+00:00", "Asia/Dubai"); expect(s).toContain("20:00"); expect(s).toMatch(/GMT\+4|GST/); });
  it("returns n/a for invalid input", () => { expect(fmtTime("garbage", "Asia/Dubai")).toBe("n/a"); expect(countdown(undefined)).toBe("n/a"); });
  it("computes countdown", () => { const now = Date.parse("2026-03-13T10:00:00Z"); expect(countdown("2026-03-13T13:30:00Z", now)).toBe("3h 30m"); expect(countdown("2026-03-16T13:30:00Z", now)).toBe("3d 3h"); });
  it("labels statuses", () => { expect(statusLabel("BUY_SETUP")).toBe("BUY SETUP"); });
});
