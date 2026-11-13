"use client";

import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";

import { USER_TYPES, type UserListParams } from "@/features/users/api/users.schemas";

export const USER_STATUSES = ["active", "inactive"] as const;
export type UserStatus = (typeof USER_STATUSES)[number];

const ROLE_PATTERN = /^[a-z_]{1,40}$/;

/**
 * ADMN-001 · The people list's place in the URL: search, type, role and active or not —
 * shareable as a link.
 */
export function useUserListParams(): {
  params: Omit<UserListParams, "cursor">;
  status: UserStatus | null;
  activeFilterCount: number;
  setFilters: (patch: {
    q?: string;
    userType?: UserListParams["userType"];
    role?: string | null;
    status?: UserStatus | null;
  }) => void;
  resetFilters: () => void;
} {
  const [values, setValues] = useQueryStates({
    q: parseAsString.withDefault(""),
    type: parseAsStringLiteral(USER_TYPES),
    role: parseAsString,
    status: parseAsStringLiteral(USER_STATUSES),
  });
  const role = values.role !== null && ROLE_PATTERN.test(values.role) ? values.role : null;
  const params = {
    q: values.q.trim(),
    userType: values.type,
    role,
    active: values.status === null ? null : values.status === "active",
  };
  const activeFilterCount =
    (params.q === "" ? 0 : 1) +
    (params.userType === null ? 0 : 1) +
    (role === null ? 0 : 1) +
    (values.status === null ? 0 : 1);

  return {
    params,
    status: values.status,
    activeFilterCount,
    setFilters: (patch) => {
      void setValues({
        ...(patch.q === undefined ? {} : { q: patch.q === "" ? null : patch.q }),
        ...(patch.userType === undefined ? {} : { type: patch.userType }),
        ...(patch.role === undefined ? {} : { role: patch.role }),
        ...(patch.status === undefined ? {} : { status: patch.status }),
      });
    },
    resetFilters: () => {
      void setValues({ q: null, type: null, role: null, status: null });
    },
  };
}
