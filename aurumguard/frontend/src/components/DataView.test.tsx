import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DataView, fmtAge, formatScalar, label, summarize } from "./DataView";

describe("DataView helpers", () => {
  it("turns keys into readable labels but keeps codes", () => {
    expect(label("freshness_seconds")).toBe("Freshness seconds");
    expect(label("expectancy_r_ci95_bootstrap")).toBe("Expectancy r ci95 bootstrap");
    expect(label("M5")).toBe("M5");
    expect(label("OOS")).toBe("OOS");
  });
  it("formats scalars for people, not machines", () => {
    expect(formatScalar(null)).toBe("–");
    expect(formatScalar(true)).toBe("Yes");
    expect(formatScalar(0.18921)).toBe("0.1892");
    expect(formatScalar(2216.4312)).toBe("2,216.43");
    expect(formatScalar("2026-09-08T12:13:41.833944+00:00", "UTC")).toContain("2026");
    expect(formatScalar("2026-09-08T12:13:41.833944+00:00", "UTC")).not.toContain("T12:13");
    expect(formatScalar("VALID")).toBe("VALID");
  });
  it("summarises nested values on one line", () => {
    const s = summarize({ status: "VALID", freshness_seconds: 221.8, issues: [] });
    expect(s).toBe("Status: VALID; Freshness seconds: 221.80; Issues: none");
    expect(summarize({ a: "x".repeat(300) }, "UTC", 40).length).toBe(40);
  });
  it("formats ages", () => {
    expect(fmtAge(0)).toBe("0s");
    expect(fmtAge(221.8)).toBe("3m 42s");
    expect(fmtAge(44021)).toBe("12h 13m");
    expect(fmtAge(null)).toBe("–");
  });
});

describe("DataView rendering", () => {
  it("renders objects as label/value tables, nested objects included", () => {
    render(<DataView value={{ quote: { subject: "quote:XAUUSD:mock", status: "VALID", freshness_seconds: 0, issues: [] } }} tz="UTC" />);
    expect(screen.getByText("Quote")).toBeInTheDocument();
    expect(screen.getByText("Freshness seconds")).toBeInTheDocument();
    expect(screen.getByText("VALID")).toBeInTheDocument();
    expect(document.querySelector("pre")).toBeNull();
    expect(document.body.textContent).not.toContain("{");
  });
  it("renders arrays of records as a table with one column per field", () => {
    render(<DataView value={[{ bucket: "50-60", n: 12, hit_rate: 0.5 }, { bucket: "60-70", n: 9, hit_rate: 0.667 }]} tz="UTC" />);
    expect(screen.getByRole("columnheader", { name: "Hit rate" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByText("0.6670")).toBeInTheDocument();
  });
  it("shows None for empty values", () => {
    render(<DataView value={null} />);
    expect(screen.getByText("None")).toBeInTheDocument();
  });
});

describe("DataView collapsing", () => {
  it("collapses large nested blocks but keeps the top level open", () => {
    const big = Object.fromEntries(Array.from({ length: 10 }, (_, i) => [`feature_${i}`, i]));
    render(<DataView value={{ M5: big, H1: big }} tz="UTC" />);
    expect(screen.getByText("M5")).toBeInTheDocument();
    const details = document.querySelectorAll("details");
    expect(details).toHaveLength(2);
    expect(details[0].textContent).toContain("10 fields");
    expect(details[0].open).toBe(false);
  });
  it("does not collapse small nested blocks", () => {
    render(<DataView value={{ quote: { status: "VALID", freshness_seconds: 0 } }} tz="UTC" />);
    expect(document.querySelectorAll("details")).toHaveLength(0);
    expect(screen.getByText("Freshness seconds")).toBeInTheDocument();
  });
});
