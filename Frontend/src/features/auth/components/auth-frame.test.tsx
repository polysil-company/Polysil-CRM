import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthFrame } from "./auth-frame";

describe("[APP-013] The sign-in frame: Polysil Sarthi and its vision", () => {
  it("names the software with its tagline beside the logo", () => {
    render(
      <AuthFrame>
        <p>The form</p>
      </AuthFrame>,
    );

    const main = screen.getByRole("main");
    expect(within(main).getByText("Polysil Sarthi")).toBeInTheDocument();
    expect(within(main).getByText("Your Digital Business Partner")).toBeInTheDocument();
    expect(within(main).getByText("The form")).toBeInTheDocument();
    expect(screen.queryByText("CRM & DMS")).not.toBeInTheDocument();
  });

  it("highlights the vision with the chariot, spoken in plain words", () => {
    render(
      <AuthFrame>
        <p>The form</p>
      </AuthFrame>,
    );

    // The card under the form, for phones.
    const card = screen.getByRole("region", { name: "Our vision" });
    expect(within(card).getByText("To Be The Sa₹thi of Farmer's Success")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(within(card).getByText("To be the Sarthi of farmer's success")).toHaveClass("sr-only");
    expect(
      within(card).getByRole("img", { name: /the Sarthi, or charioteer/ }),
    ).toBeInTheDocument();

    // The brand panel, for wide screens.
    const panel = screen.getByRole("complementary", { name: "About Polysil Sarthi" });
    expect(within(panel).getByText("Your Digital Business Partner")).toBeInTheDocument();
    expect(within(panel).getByText("Our vision")).toBeInTheDocument();
  });
});
