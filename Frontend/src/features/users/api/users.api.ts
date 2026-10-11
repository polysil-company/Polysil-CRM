import { z } from "zod";

import { apiDownload, apiRequest, type DownloadedFile } from "@/lib/api/client";
import type { ApiPath } from "@/lib/api/url";
import { createLogger } from "@/lib/logger";

import {
  handoverResultSchema,
  officePageSchema,
  passwordSetResultSchema,
  revokeResultSchema,
  roleListSchema,
  unlockResultSchema,
  userDetailSchema,
  userPageSchema,
  type CreateUserRequest,
  type HandoverRequest,
  type HandoverResult,
  type OfficeChoice,
  type PatchUserRequest,
  type RoleItem,
  type UserDetail,
  type UserListParams,
  type UserPage,
} from "./users.schemas";

const log = createLogger({ file: "features/users/api/users.api.ts", dataId: "ADMN-001" });

export const USER_PAGE_SIZE = 25;

function userPath(userId: string, rest = ""): ApiPath {
  return `/users/${encodeURIComponent(userId)}${rest}`;
}

function filterQuery(params: UserListParams): Record<string, string | boolean | undefined> {
  return {
    q: params.q.trim() === "" ? undefined : params.q.trim(),
    user_type: params.userType ?? undefined,
    role: params.role ?? undefined,
    is_active: params.active ?? undefined,
  };
}

function logSkipped(fn: string, skipped: number, kept: number): void {
  if (skipped > 0) {
    log.warn(fn, `left out ${String(skipped)} row(s) that did not match the contract`, {
      dataId: "ADMN-001",
      context: { skipped, kept },
    });
  }
}

/** ADMN-001 · GET /users — staff and partner users in scope, newest first, filtered. */
export async function listUsers(params: UserListParams, signal?: AbortSignal): Promise<UserPage> {
  const page = await apiRequest({
    dataId: "ADMN-001",
    logger: log,
    fn: "listUsers",
    path: "/users",
    query: {
      ...filterQuery(params),
      cursor: params.cursor ?? undefined,
      limit: USER_PAGE_SIZE,
      include_total: params.cursor === null,
    },
    schema: userPageSchema,
    signal,
  });
  logSkipped("listUsers", page.skipped, page.items.length);
  return page;
}

/**
 * ADMN-001 · GET /users/export — the list as an Excel file, with the same filters: every
 * page, nothing outside the caller's scope. More than 5,000 rows is `422 export_too_large`.
 */
export function exportUsers(params: UserListParams): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "ADMN-001",
    logger: log,
    fn: "exportUsers",
    path: "/users/export",
    query: filterQuery(params),
  });
}

/** ADMN-002 · GET /users/{id} */
export function getUser(userId: string, signal?: AbortSignal): Promise<UserDetail> {
  return apiRequest({
    dataId: "ADMN-002",
    logger: log,
    fn: "getUser",
    path: userPath(userId),
    schema: userDetailSchema,
    signal,
  });
}

/**
 * ADMN-003 · POST /users. A staff member's temporary password is in the body, so the request
 * is logged without it.
 */
export function createUser({
  body,
  idempotencyKey,
}: {
  body: CreateUserRequest;
  idempotencyKey: string;
}): Promise<UserDetail> {
  return apiRequest({
    dataId: "ADMN-003",
    logger: log,
    fn: "createUser",
    method: "POST",
    path: "/users",
    body,
    idempotencyKey,
    schema: userDetailSchema,
    sensitive: true,
  });
}

/** ADMN-004 · PATCH /users/{id} — only what changes; `is_active` deactivates or reactivates. */
export function patchUser({
  userId,
  body,
  idempotencyKey,
}: {
  userId: string;
  body: PatchUserRequest;
  idempotencyKey: string;
}): Promise<UserDetail> {
  return apiRequest({
    dataId: "ADMN-004",
    logger: log,
    fn: "patchUser",
    method: "PATCH",
    path: userPath(userId),
    body,
    idempotencyKey,
    schema: userDetailSchema,
  });
}

/** ADMN-005 · POST /users/{id}/password — a new temporary password; every session ends. */
export function setTemporaryPassword({
  userId,
  password,
  idempotencyKey,
}: {
  userId: string;
  password: string;
  idempotencyKey: string;
}): Promise<{ sessionsRevoked: number }> {
  return apiRequest({
    dataId: "ADMN-005",
    logger: log,
    fn: "setTemporaryPassword",
    method: "POST",
    path: userPath(userId, "/password"),
    body: { password },
    idempotencyKey,
    schema: passwordSetResultSchema,
    sensitive: true,
  });
}

/** ADMN-005 · POST /users/{id}/sessions/revoke — sign the person out everywhere, now. */
export function revokeSessions({
  userId,
  idempotencyKey,
}: {
  userId: string;
  idempotencyKey: string;
}): Promise<{ sessionsRevoked: number }> {
  return apiRequest({
    dataId: "ADMN-005",
    logger: log,
    fn: "revokeSessions",
    method: "POST",
    path: userPath(userId, "/sessions/revoke"),
    idempotencyKey,
    schema: revokeResultSchema,
  });
}

/** ADMN-005 · POST /users/{id}/unlock — clear a sign-in lockout before its fifteen minutes. */
export function unlockUser({
  userId,
  idempotencyKey,
}: {
  userId: string;
  idempotencyKey: string;
}): Promise<{ wasLocked: boolean }> {
  return apiRequest({
    dataId: "ADMN-005",
    logger: log,
    fn: "unlockUser",
    method: "POST",
    path: userPath(userId, "/unlock"),
    idempotencyKey,
    schema: unlockResultSchema,
  });
}

/**
 * ADMN-006 · POST /users/{id}/handover — moves at most 500 open leads (and every open task) per
 * call; repeat with a new key while `remaining` is above 0.
 */
export function handOver({
  userId,
  body,
  idempotencyKey,
}: {
  userId: string;
  body: HandoverRequest;
  idempotencyKey: string;
}): Promise<HandoverResult> {
  return apiRequest({
    dataId: "ADMN-006",
    logger: log,
    fn: "handOver",
    method: "POST",
    path: userPath(userId, "/handover"),
    body,
    idempotencyKey,
    schema: handoverResultSchema,
  });
}

/** ADMN-006 · DELETE /users/{id} — soft delete; refused while they own open leads. */
export function deleteUser({
  userId,
  idempotencyKey,
}: {
  userId: string;
  idempotencyKey: string;
}): Promise<undefined> {
  return apiRequest({
    dataId: "ADMN-006",
    logger: log,
    fn: "deleteUser",
    method: "DELETE",
    path: userPath(userId),
    idempotencyKey,
    schema: z.undefined(),
  });
}

/** ADMN-003 · GET /lookups/roles — the sixteen roles; the staff form leaves out portal ones. */
export function listRoles(signal?: AbortSignal): Promise<RoleItem[]> {
  return apiRequest({
    dataId: "ADMN-003",
    logger: log,
    fn: "listRoles",
    path: "/lookups/roles",
    schema: roleListSchema,
    signal,
  });
}

/** ADMN-003 · GET /org-units?is_open=true — open offices by name, for the office picker. */
export async function searchOpenOffices(q: string, signal?: AbortSignal): Promise<OfficeChoice[]> {
  const page = await apiRequest({
    dataId: "ADMN-003",
    logger: log,
    fn: "searchOpenOffices",
    path: "/org-units",
    query: { q: q.trim() === "" ? undefined : q.trim(), is_open: true, limit: 50 },
    schema: officePageSchema,
    signal,
  });
  return [...page.items];
}
