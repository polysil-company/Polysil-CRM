import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError, type ApiErrorInit } from "@/lib/api/errors";

import { ErrorState } from "./error-state";

function apiError(init: Partial<ApiErrorInit>): ApiError {
  return new ApiError({
    kind: "http",
    status: 500,
    message: "failed",
    dataId: "LEAD-001",
    requestId: "req-1",
    method: "GET",
    path: "/leads",
    ...init,
  });
}

describe("[DS-001] ErrorState", () => {
  it("explains a server error, offers retry and a copyable reference", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorState error={apiError({})} onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong on our side");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    expect(screen.getByText("LEAD-001 · req-1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy reference" }));
    await expect(navigator.clipboard.readText()).resolves.toBe("LEAD-001 · req-1");
    expect(await screen.findByRole("button", { name: "Reference copied" })).toBeInTheDocument();
  });

  it("does not offer a retry that cannot help", () => {
    render(
      <ErrorState
        error={apiError({ kind: "contract", code: "CONTRACT_VIOLATION" })}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("We received data we couldn't read");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("uses generic copy and no reference for unexpected errors", () => {
    render(<ErrorState error={new TypeError("x is undefined")} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.queryByText(/·/)).not.toBeInTheDocument();
  });
});
