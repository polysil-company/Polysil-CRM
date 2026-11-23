import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Dialog } from "@/components/ui/dialog";
import { Toaster } from "@/components/ui/sonner";
import { mockDb, resetMockDb } from "@/mocks/db";
import { renderWithProviders } from "@/test/render";

import { EmailPreferencesDialogContent } from "./email-preferences-dialog";

describe("[AUTH-008] EmailPreferencesDialogContent", () => {
  it("turns the morning summary off, and saves both switches", async () => {
    resetMockDb();
    const onDone = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <Dialog open>
          <EmailPreferencesDialogContent notices morningSummary onDone={onDone} />
        </Dialog>
        <Toaster />
      </>,
    );

    const form = await screen.findByRole("form", { name: "Email preferences" });
    await user.click(within(form).getByRole("checkbox", { name: /Morning summary/ }));
    await user.click(within(form).getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Email preferences saved")).toBeInTheDocument();
    expect(mockDb.emailPreferences).toEqual({ notices: true, morning_summary: false });
    expect(onDone).toHaveBeenCalled();
  });
});
