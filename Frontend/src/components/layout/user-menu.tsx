"use client";

import {
  Alert02Icon,
  Bug01Icon,
  FlaskConicalIcon,
  Logout03Icon,
  UserMultiple02Icon,
} from "@hugeicons/core-free-icons";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { Avatar, AvatarFallback, getInitials } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/session/hooks/use-session";
import { CHANNEL_PARTNER_TYPE_LABELS, ROLE_LABELS, ROLES, type Role } from "@/lib/auth/roles";
import {
  MOCK_SCENARIO_LABELS,
  MOCK_SCENARIOS,
  readMockRole,
  readMockScenario,
  writeMockRole,
  writeMockScenario,
  type MockScenario,
} from "@/lib/dev/mock-settings";
import { clientEnv } from "@/lib/env/client";
import {
  isLogLevel,
  LOG_LEVELS,
  readBrowserLogLevelOverride,
  setBrowserLogLevelOverride,
  type LogLevel,
} from "@/lib/logger";

export function UserMenu(): React.JSX.Element {
  const session = useSession();

  if (session.status === "pending") {
    return <Skeleton className="size-8 rounded-full" />;
  }

  if (session.status === "error") {
    return (
      <Button
        variant="ghost"
        size="icon-md"
        aria-label="Your account could not be loaded. Try again."
        onClick={() => {
          void session.refetch();
        }}
      >
        <Icon icon={Alert02Icon} className="text-danger" />
      </Button>
    );
  }

  const { user } = session.data;
  const roleLabel =
    session.data.role === "channel_partner"
      ? `${CHANNEL_PARTNER_TYPE_LABELS[session.data.partner.type]} · ${session.data.partner.name}`
      : ROLE_LABELS[session.data.role];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon-md"
            className="rounded-full"
            aria-label={`Account menu for ${user.name}`}
          />
        }
      >
        <Avatar size="sm">
          <AvatarFallback>{getInitials(user.name)}</AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <div className="flex flex-col px-2 py-1.5">
          <span className="truncate text-sm font-medium text-foreground">{user.name}</span>
          <span className="truncate text-xs text-muted-foreground">{roleLabel}</span>
        </div>
        <DropdownMenuSeparator />
        {clientEnv.apiMocking === "enabled" ? (
          <>
            <MockControls />
            <DropdownMenuSeparator />
          </>
        ) : null}
        {clientEnv.appEnv === "production" ? null : (
          <>
            <LogLevelControl />
            <DropdownMenuSeparator />
          </>
        )}
        {/* TODO(AUTH-001): wire sign-out once the auth contract is agreed. */}
        <DropdownMenuItem disabled>
          <Icon icon={Logout03Icon} />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Developer controls for the mock backend: preview any role or any data state. */
function MockControls(): React.JSX.Element {
  const queryClient = useQueryClient();
  const [role, setRole] = useState<Role>(readMockRole);
  const [scenario, setScenario] = useState<MockScenario>(readMockScenario);

  return (
    <>
      <DropdownMenuLabel>Mock backend</DropdownMenuLabel>
      <DropdownMenuSub>
        <DropdownMenuSubTrigger>
          <Icon icon={UserMultiple02Icon} />
          Preview as role
        </DropdownMenuSubTrigger>
        <DropdownMenuContent side="right" align="start" sideOffset={4} className="w-56">
          <DropdownMenuRadioGroup
            value={role}
            onValueChange={(value: unknown) => {
              const next = ROLES.find((candidate) => candidate === value);
              if (next === undefined) {
                return;
              }
              writeMockRole(next);
              setRole(next);
              void queryClient.invalidateQueries();
            }}
          >
            {ROLES.map((item) => (
              <DropdownMenuRadioItem key={item} value={item}>
                {ROLE_LABELS[item]}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenuSub>
      <DropdownMenuSub>
        <DropdownMenuSubTrigger>
          <Icon icon={FlaskConicalIcon} />
          Data scenario
        </DropdownMenuSubTrigger>
        <DropdownMenuContent side="right" align="start" sideOffset={4} className="w-56">
          <DropdownMenuRadioGroup
            value={scenario}
            onValueChange={(value: unknown) => {
              const next = MOCK_SCENARIOS.find((candidate) => candidate === value);
              if (next === undefined) {
                return;
              }
              writeMockScenario(next);
              setScenario(next);
              // Reset (not just refetch) so every screen shows its loading state again.
              void queryClient.resetQueries();
            }}
          >
            {MOCK_SCENARIOS.map((item) => (
              <DropdownMenuRadioItem key={item} value={item}>
                {MOCK_SCENARIO_LABELS[item]}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenuSub>
    </>
  );
}

const FOLLOW_SERVER = "server";

const LOG_LEVEL_LABELS: Readonly<Record<LogLevel, string>> = {
  debug: "Debug — everything",
  info: "Info",
  warn: "Warnings and errors",
  error: "Errors only",
  silent: "Off",
};

/** This browser's console log level. In production use `polysilLogger.setLevel()` from the console. */
function LogLevelControl(): React.JSX.Element {
  const [level, setLevel] = useState<LogLevel | typeof FOLLOW_SERVER>(
    () => readBrowserLogLevelOverride() ?? FOLLOW_SERVER,
  );

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger>
        <Icon icon={Bug01Icon} />
        Console logs
      </DropdownMenuSubTrigger>
      <DropdownMenuContent side="right" align="start" sideOffset={4} className="w-56">
        <DropdownMenuRadioGroup
          value={level}
          onValueChange={(value: unknown) => {
            if (value === FOLLOW_SERVER) {
              setBrowserLogLevelOverride(null);
              setLevel(FOLLOW_SERVER);
              return;
            }
            if (isLogLevel(value)) {
              setBrowserLogLevelOverride(value);
              setLevel(value);
            }
          }}
        >
          <DropdownMenuRadioItem value={FOLLOW_SERVER}>Follow LOG_LEVEL</DropdownMenuRadioItem>
          {LOG_LEVELS.map((item) => (
            <DropdownMenuRadioItem key={item} value={item}>
              {LOG_LEVEL_LABELS[item]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenuSub>
  );
}
