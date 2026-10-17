import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as React from "react";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { codeFromName, createRequestOf, draftProblems } from "./lookup-list-panel";
import { Masters } from "./masters";
import { changedSettings, settingProblem, settingText } from "./scoring-panel";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(ui: React.JSX.Element, searchParams = ""): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      {ui}
      <Toaster />
    </>,
    { searchParams },
  );
  return user;
}

function reset(): void {
  resetMockDb();
  writeMockRole("state_manager");
}

describe("[MSTR-009] Masters lists", () => {
  afterEach(reset);

  it("lists a list's rows, switched-off ones too, read-only without masters.edit", async () => {
    signInAs("employee");
    show(<Masters />);

    const table = await screen.findByRole("table", { name: "Lead sources" });
    expect(within(table).getByRole("rowheader", { name: "Agri Fair" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add a lead source/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Switch off/ })).not.toBeInTheDocument();
  });

  it("adds a lead source, its code following the name until typed", async () => {
    signInAs("admin");
    const user = show(<Masters />);
    await user.click(await screen.findByRole("button", { name: "Add a lead source" }));
    const form = await screen.findByRole("form", { name: "Add a lead source" });

    await user.click(within(form).getByRole("button", { name: "Add" }));
    expect(within(form).getByText("Enter the name.")).toBeInTheDocument();

    await user.type(within(form).getByRole("textbox", { name: "Name" }), "Krishi Mela 2026");
    expect(within(form).getByRole("textbox", { name: "Code" })).toHaveValue("krishi_mela_2026");
    await user.type(within(form).getByRole("textbox", { name: "Quality (optional)" }), "0.6");
    await user.click(within(form).getByRole("button", { name: "Add" }));

    expect(await screen.findByText("Krishi Mela 2026 added")).toBeInTheDocument();
    expect(mockDb.lookups["lead-sources"].some((row) => row.code === "krishi_mela_2026")).toBe(
      true,
    );
    expect(await screen.findByRole("rowheader", { name: "Krishi Mela 2026" })).toBeInTheDocument();
  });

  it("switches a row off from its tab, and says what that means", async () => {
    signInAs("admin");
    const user = show(<Masters />, "?tab=complaint-types");
    await user.click(await screen.findByRole("button", { name: "Switch off Components" }));

    expect(await screen.findByText("Components switched off")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        mockDb.lookups["complaint-types"].find((row) => row.code === "components")?.is_active,
      ).toBe(false);
    });
    expect(await screen.findByRole("button", { name: "Switch on Components" })).toBeInTheDocument();
  });
});

describe("[MSTR-009] The add form's rules", () => {
  const empty = {
    name: "",
    code: "",
    codeTouched: false,
    sortOrder: "",
    quality: "",
    kind: "lost" as const,
  };

  it("makes a code from a name", () => {
    expect(codeFromName("Agri Fair (Rajkot)")).toBe("agri_fair_rajkot");
    expect(codeFromName("  OEM's components ")).toBe("oem_s_components");
  });

  it("names what is wrong before sending", () => {
    expect(
      draftProblems("lead-sources", { ...empty, code: "Agri Fair", quality: "2" }, []),
    ).toEqual({
      name: "Enter the name.",
      code: "Lowercase letters, digits and underscores only, like agri_fair.",
      quality: "A number from 0 to 1, like 0.6.",
    });
  });

  it("sends only the fields a list takes", () => {
    const draft = { ...empty, name: "Price", code: "price_2", sortOrder: "5", quality: "0.4" };
    expect(createRequestOf("crops", draft)).toEqual({ code: "price_2", name: "Price" });
    expect(createRequestOf("lost-reasons", draft)).toEqual({
      code: "price_2",
      name: "Price",
      sort_order: 5,
      kind: "lost",
    });
  });
});

describe("[MSTR-010] Lead scoring", () => {
  afterEach(reset);

  it("saves only the settings that changed", async () => {
    signInAs("admin");
    const user = show(<Masters />, "?tab=scoring");
    const hot = await screen.findByRole("textbox", { name: "Hot from" });
    expect(hot).toHaveValue("70");
    expect(
      screen.getByText("The weights add up to 100: the most a lead can score."),
    ).toBeInTheDocument();

    await user.clear(hot);
    await user.type(hot, "75");
    expect(screen.getByText("1 setting changed.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save the settings" }));

    expect(await screen.findByText("Score settings saved")).toBeInTheDocument();
    expect(mockDb.scoring.find((item) => item.key === "threshold_hot")?.value).toBe("75.00");
  });

  it("refuses a cap of zero on its field", async () => {
    signInAs("admin");
    const user = show(<Masters />, "?tab=scoring");
    const cap = await screen.findByRole("textbox", { name: "Value cap (₹)" });
    await user.clear(cap);
    await user.type(cap, "0");
    await user.click(screen.getByRole("button", { name: "Save the settings" }));

    expect(screen.getByText("Must be more than 0.")).toBeInTheDocument();
    expect(mockDb.scoring.find((item) => item.key === "value_cap")?.value).toBe("500000.00");
  });

  it("shows the settings read-only without masters.edit", async () => {
    signInAs("employee");
    show(<Masters />, "?tab=scoring");
    expect(await screen.findByRole("textbox", { name: "Hot from" })).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: "Save the settings" })).not.toBeInTheDocument();
  });

  it("reads and checks a setting's text", () => {
    expect(settingText("25.00")).toBe("25");
    expect(settingText("0.50")).toBe("0.5");
    expect(settingProblem("w_value", "0")).toBeNull();
    expect(settingProblem("speed_fast_hours", "0")).toBe("Must be more than 0.");
    expect(settingProblem("w_value", "abc")).toBe("A number, up to two decimals.");
    expect(
      changedSettings(
        [
          { key: "w_value", value: "35.00" },
          { key: "w_speed", value: "20.00" },
        ],
        { w_value: "35", w_speed: "25" },
      ),
    ).toEqual({ w_speed: "25" });
  });
});
