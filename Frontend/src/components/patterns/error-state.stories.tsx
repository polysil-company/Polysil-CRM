import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";

import { ApiError } from "@/lib/api/errors";

import { ErrorReference, ErrorState } from "./error-state";

const REQUEST_ID = "3f2a9c1e-7b1d-4c55-9a0e-2d7c1f0b8e61";

const serverError = new ApiError({
  kind: "http",
  message: "Service Unavailable",
  dataId: "LEAD-001",
  requestId: REQUEST_ID,
  method: "GET",
  path: "/leads",
  status: 503,
});

const offline = new ApiError({
  kind: "network",
  message: "Failed to fetch",
  dataId: "LEAD-001",
  requestId: REQUEST_ID,
  method: "GET",
  path: "/leads",
});

const contractViolation = new ApiError({
  kind: "contract",
  message: "The response did not match the agreed schema",
  dataId: "RPT-001",
  requestId: REQUEST_ID,
  method: "GET",
  path: "/dashboard/overview",
  status: 200,
  code: "CONTRACT_VIOLATION",
});

const forbidden = new ApiError({
  kind: "http",
  message: "Forbidden",
  dataId: "LEAD-003",
  requestId: REQUEST_ID,
  method: "GET",
  path: "/leads/lead-10001",
  status: 403,
});

const meta = {
  title: "Patterns/ErrorState",
  component: ErrorState,
  args: { error: serverError, onRetry: fn() },
  argTypes: { error: { control: false } },
} satisfies Meta<typeof ErrorState>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Retryable: offers "Try again". The reference finds the request in frontend and backend logs. */
export const ServerError: Story = {};

export const Offline: Story = {
  args: { error: offline },
};

/** The backend answered, but not in the agreed shape. Retrying cannot help, so there is no retry. */
export const ContractViolation: Story = {
  args: { error: contractViolation },
};

export const NoPermission: Story = {
  args: { error: forbidden },
};

/** Not an API error — a bug. Generic copy and no reference. */
export const UnexpectedError: Story = {
  args: { error: new Error("Cannot read properties of undefined") },
};

export const Reference: Story = {
  render: () => <ErrorReference reference={`LEAD-001 · ${REQUEST_ID}`} />,
};
