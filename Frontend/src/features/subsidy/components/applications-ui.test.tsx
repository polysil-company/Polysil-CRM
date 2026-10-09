import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { getLead } from "@/features/leads/api/leads.api";
import type { LeadWire } from "@/features/leads/api/leads.schemas";
import { listApplications } from "@/features/subsidy/api/subsidy-applications.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ApplicationDetail } from "./application-detail";
import { ApplicationsList } from "./applications-list";
import { LeadSubsidy } from "./lead-subsidy";
import { StartApplication } from "./start-application";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), notFound: vi.fn() }));

/** The calculation waits for typing to pause. */
const SETTLE = { timeout: 3000 };

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(ui: React.JSX.Element): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      {ui}
      <Toaster />
    </>,
  );
  return user;
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  push.mockReset();
}

async function openApplicationId(): Promise<string> {
  const page = await listApplications({
    status: "open",
    stage: null,
    q: "",
    leadId: null,
    cursor: null,
  });
  const first = page.items[0];
  if (first === undefined) throw new Error("No open application in the seed");
  return first.id;
}

/** A second qualified lead, made subsidised drip, other than the one given. */
function forwardableLeadOther(otherThan: string): string {
  const lead = mockDb.leads.find((item) => item.stage === "qualified" && item.id !== otherThan);
  if (lead === undefined) throw new Error("No second qualified lead");
  lead.inquiry_type = "subsidised";
  lead.mis_system = "drip";
  return lead.id;
}

/** A qualified lead made into a subsidised drip enquiry. */
function forwardableLead(): LeadWire {
  const lead = mockDb.leads.find((item) => item.stage === "qualified");
  if (lead === undefined) throw new Error("No qualified lead");
  lead.inquiry_type = "subsidised";
  lead.mis_system = "drip";
  return lead;
}

describe("[SUBS-005] ApplicationsList", () => {
  afterEach(reset);

  it("lists each application with its farmer, stage and subsidy", async () => {
    signInAs("employee");
    show(<ApplicationsList />);
    const list = await screen.findByRole("list", { name: "Subsidy applications" });
    const rows = within(list).getAllByRole("link");
    expect(rows.length).toBeGreaterThan(2);
    expect(within(list).getByText("Cancelled")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download Excel/ })).toBeInTheDocument();
  });
});

describe("[SUBS-006] ApplicationDetail", () => {
  afterEach(reset);

  it("records the next stage, and wants a remark to record the current one again", async () => {
    signInAs("employee");
    const id = await openApplicationId();
    const user = show(<ApplicationDetail applicationId={id} />);

    expect(await screen.findByRole("list", { name: "Stage history" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Record stage" }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByLabelText(/^Happened on/);

    // The current stage is chosen first: recording it again needs a remark.
    await user.click(within(dialog).getByRole("button", { name: "Record stage" }));
    expect(
      await within(dialog).findByText("Say why this stage is recorded again."),
    ).toBeInTheDocument();

    await user.click(within(dialog).getByRole("combobox", { name: "Stage" }));
    await user.click(await screen.findByRole("option", { name: /^14\. FP invoice submitted/ }));
    await user.type(within(dialog).getByRole("textbox", { name: /^FP Amount/ }), "1250.505");
    await user.click(within(dialog).getByRole("button", { name: "Record stage" }));
    expect(await within(dialog).findByText("At most two decimals (paise).")).toBeInTheDocument();

    const amount = within(dialog).getByRole("textbox", { name: /^FP Amount/ });
    await user.clear(amount);
    await user.type(amount, "1250.50");
    await user.click(within(dialog).getByRole("button", { name: "Record stage" }));

    expect(await screen.findByText("FP invoice submitted recorded")).toBeInTheDocument();
    const history = await screen.findByRole("list", { name: "Stage history" });
    expect(await within(history).findByText("₹1,250.50")).toBeInTheDocument();
  });

  it("cancels with a reason", async () => {
    signInAs("employee");
    const id = await openApplicationId();
    const user = show(<ApplicationDetail applicationId={id} />);

    await user.click(await screen.findByRole("button", { name: "Cancel application" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel application" }));
    expect(await within(dialog).findByText("Say why it is cancelled.")).toBeInTheDocument();
    await user.type(within(dialog).getByRole("textbox", { name: "Reason" }), "Farmer withdrew");
    await user.click(within(dialog).getByRole("button", { name: "Cancel application" }));

    expect(await screen.findByText("Application cancelled")).toBeInTheDocument();
    expect(await screen.findByText("Farmer withdrew")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record stage" })).not.toBeInTheDocument();
  });

  it("lets a view-only Regional Manager download the PIMS sheet but change nothing", async () => {
    signInAs("regional_manager");
    const id = await openApplicationId();
    show(<ApplicationDetail applicationId={id} />);

    expect(await screen.findByRole("button", { name: "PIMS sheet" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record stage" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel application" })).not.toBeInTheDocument();
    const checklist = await screen.findByRole("list", { name: "Document checklist" });
    expect(within(checklist).queryAllByRole("button", { name: /^Add a file/ })).toHaveLength(0);
  });

  it("offers the PIMS sheet only on a GGRC application", async () => {
    signInAs("employee");
    const id = await openApplicationId();
    const application = mockDb.subsidyApplications?.find((row) => row.id === id);
    if (application === undefined) throw new Error("No application");
    application.scheme = "UPMIS";
    show(<ApplicationDetail applicationId={id} />);
    expect(await screen.findByRole("button", { name: "Record stage" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "PIMS sheet" })).not.toBeInTheDocument();
  });

  it("refuses a file over 10 MB before sending it", async () => {
    signInAs("employee");
    const id = await openApplicationId();
    const user = show(<ApplicationDetail applicationId={id} />);

    const checklist = await screen.findByRole("list", { name: "Document checklist" });
    await user.click(within(checklist).getByRole("button", { name: "Add a file to Form No. 16" }));
    const big = new File([new Uint8Array(11 * 1024 * 1024)], "survey.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(screen.getByTestId("application-file-input"), { target: { files: [big] } });
    expect(await screen.findByText("One file wasn't added")).toBeInTheDocument();
  });
});

describe("[SUBS-004] Start a subsidy application", () => {
  afterEach(reset);

  it("offers it on a subsidised lead, then starts it from the calculation and a category", async () => {
    signInAs("employee");
    const wire = forwardableLead();
    const lead = await getLead(wire.id);
    const user = show(
      <>
        <LeadSubsidy lead={lead} />
        <StartApplication leadId={wire.id} />
      </>,
    );

    expect(await screen.findByRole("link", { name: "Start subsidy application" })).toHaveAttribute(
      "href",
      `/subsidy/new?lead=${wire.id}`,
    );

    await user.type(await screen.findByRole("textbox", { name: /^Area/ }), "1.5");
    await user.type(screen.getByRole("textbox", { name: /^Lateral spacing/ }), "2");
    // Nothing to start until the figures are in; then a category is asked for.
    expect(screen.getByRole("button", { name: "Start application" })).toBeDisabled();
    const small = await screen.findByRole("radio", { name: /Small Farmer 70 %/ }, SETTLE);
    await user.click(screen.getByRole("button", { name: "Start application" }));
    expect(await screen.findByText("Choose the farmer's category.")).toBeInTheDocument();

    await user.click(small);
    await user.type(screen.getByRole("textbox", { name: /^Survey No/ }), "112/2");
    await user.click(screen.getByRole("button", { name: "Start application" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(expect.stringMatching(/^\/subsidy\/[\w-]+$/));
    });
    expect(wire.stage).toBe("won");
  });

  it("says when the lead's state has no subsidy scheme set up", async () => {
    signInAs("employee");
    const wire = forwardableLead();
    server.use(
      http.get(buildApiUrl("/subsidy-schemes/for-lead/:leadId"), () =>
        HttpResponse.json(
          { error: { code: "no_scheme_for_state", message: "No scheme for this state." } },
          { status: 422 },
        ),
      ),
    );
    show(<StartApplication leadId={wire.id} />);
    expect(
      await screen.findByText("Subsidy for this state is not set up yet. Ask an administrator."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /^Area/ })).not.toBeInTheDocument();
  });

  it("calculates under the lead's scheme, and refuses one that isn't ready", async () => {
    signInAs("employee");
    const wire = forwardableLead();
    const asked: (string | null)[] = [];
    server.use(
      http.get(buildApiUrl("/subsidy/config"), ({ request }) => {
        asked.push(new URL(request.url).searchParams.get("scheme"));
        return undefined;
      }),
    );
    const user = show(<StartApplication leadId={wire.id} />);
    await user.type(await screen.findByRole("textbox", { name: /^Area/ }), "1");
    expect(asked).toContain("GGRC");

    server.use(
      http.get(buildApiUrl("/subsidy-schemes/for-lead/:leadId"), () =>
        HttpResponse.json({ data: { code: "UPMIS", name: "UP Micro Irrigation", ready: false } }),
      ),
    );
    show(<StartApplication leadId={forwardableLeadOther(wire.id)} />);
    expect(
      await screen.findByText("Subsidy for this state is not set up yet. Ask an administrator."),
    ).toBeInTheDocument();
  });

  it("says why a commercial lead can't start one", async () => {
    signInAs("employee");
    const wire = forwardableLead();
    wire.inquiry_type = "commercial";
    show(<StartApplication leadId={wire.id} />);
    expect(
      await screen.findByText("Only a subsidised enquiry can become an application."),
    ).toBeInTheDocument();
  });
});
