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
