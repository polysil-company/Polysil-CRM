import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/render";

import { meterToneFor, SegmentedMeter } from "./segmented-meter";
import { buildSparklinePoints, describeTrend, Sparkline } from "./sparkline";
import { TagList, toneForLabel } from "./tag";

describe("[DS-001] SegmentedMeter", () => {
  it("exposes its value as an accessible meter", () => {
    renderWithProviders(<SegmentedMeter value={62} label="Win probability" />);

    const meter = screen.getByRole("meter", { name: "Win probability" });
    expect(meter).toHaveAttribute("aria-valuenow", "62");
    expect(meter).toHaveAttribute("aria-valuetext", "62%");
  });

  it("clamps out-of-range values", () => {
    renderWithProviders(<SegmentedMeter value={140} label="Score" />);
    expect(screen.getByRole("meter", { name: "Score" })).toHaveAttribute("aria-valuenow", "100");
  });

  it("derives the tone from the value", () => {
    expect(meterToneFor(0.1)).toBe("danger");
    expect(meterToneFor(0.5)).toBe("warning");
    expect(meterToneFor(0.9)).toBe("success");
  });
});

describe("[DS-001] TagList", () => {
  const crops = ["Cotton", "Banana", "Wheat", "Onion"].map((label) => ({ id: label, label }));

  it("collapses tags beyond the limit into a labelled +N", () => {
    renderWithProviders(<TagList items={crops} max={2} />);

    expect(screen.getByText("Cotton")).toBeInTheDocument();
    expect(screen.getByText("Banana")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "2 more: Wheat, Onion" })).toHaveTextContent("+2");
  });

  it("shows the empty glyph when there are no tags", () => {
    renderWithProviders(<TagList items={[]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("gives the same label the same colour", () => {
    expect(toneForLabel("Cotton")).toBe(toneForLabel("cotton"));
  });
});

describe("[DS-001] Sparkline", () => {
  it("draws a flat series through the middle", () => {
    expect(buildSparklinePoints([3, 3, 3]).every((point) => point.y === 14)).toBe(true);
  });

  it("summarises the trend for screen readers", () => {
    expect(describeTrend([3, 5, 9], "Leads per week")).toBe("Leads per week: rising, from 3 to 9");
    expect(describeTrend([], "Leads per week")).toBe("Leads per week: no data");
  });

  it("renders an accessible image, or the empty glyph without enough points", () => {
    renderWithProviders(<Sparkline values={[1, 4, 2]} label="Visits: flat" />);
    expect(screen.getByRole("img", { name: "Visits: flat" })).toBeInTheDocument();

    renderWithProviders(<Sparkline values={[5]} label="Too short" />);
    expect(screen.queryByRole("img", { name: "Too short" })).not.toBeInTheDocument();
  });
});
