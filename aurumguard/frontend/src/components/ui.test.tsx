import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DecisionCard, StatusBadge } from "./ui";
import type { Decision } from "@/lib/types";

describe("ui", () => {
  it("renders status badge with role", () => { render(<StatusBadge status="NO_TRADE" />); expect(screen.getByRole("status")).toHaveTextContent("NO TRADE"); });
  it("renders a decision without setup", () => {
    const d: Decision = { decision_id: "abc", horizon: "INTRADAY", status: "WAIT", strategy_id: "PBC-H1", strategy_version: "1.0.0", as_of: "2026-03-10T10:00:00Z", reason: "waiting for trigger", score: 60, regime: "STRONG_TREND", demo_data: true, setup: null, expiry: null };
    render(<DecisionCard d={d} tz="Asia/Dubai" />);
    expect(screen.getByText(/waiting for trigger/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Evidence Inspector/ })).toHaveAttribute("href", "/evidence/abc");
  });
});

import { liveDataNotice } from "./Providers";

describe("liveDataNotice", () => {
  const base = { economic_calendar: { name: "mock", is_mock: true, disabled: false }, news: { name: "none", is_mock: false, disabled: true }, macro_series: { name: "mock", is_mock: true, disabled: false }, push: { name: "mock", is_mock: true, disabled: false } };
  it("is null while prices are synthetic (red DEMO banner applies instead)", () => {
    expect(liveDataNotice({ market_data: { name: "mock", is_mock: true, disabled: false }, ...base })).toBeNull();
    expect(liveDataNotice(undefined)).toBeNull();
  });
  it("names the live source and every synthetic or disabled input", () => {
    const s = liveDataNotice({ market_data: { name: "twelvedata", is_mock: false, disabled: false }, ...base })!;
    expect(s).toContain("LIVE PRICES via twelvedata");
    expect(s).toContain("synthetic: economic calendar, macro series");
    expect(s).toContain("disabled: news");
    expect(s).not.toContain("push");
  });
});
