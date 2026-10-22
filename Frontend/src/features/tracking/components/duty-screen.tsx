"use client";

import { Location01Icon, SmartPhone01Icon } from "@hugeicons/core-free-icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Notice } from "@/components/patterns/notice";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/session/hooks/use-session";
import { useEndDuty, useStartDuty } from "@/features/tracking/api/duty.mutations";
import {
  nativeDeviceQueryOptions,
  nativeKeys,
  nativePermissionsQueryOptions,
  nativeStatusQueryOptions,
} from "@/features/tracking/api/native.queries";
import { routeQueryOptions } from "@/features/tracking/api/tracking.queries";
import { useAcceptConsent } from "@/features/tracking/api/visits.mutations";
import { trackingConfigQueryOptions } from "@/features/tracking/api/visits.queries";
import type { TrackingConfig } from "@/features/tracking/api/visits.schemas";
import { getOneFix } from "@/features/tracking/hooks/use-browser-fix";
import {
  autostartHelp,
  BLOCKER_COPY,
  dutyBlockers,
  serverEndText,
  uploadProblem,
  type DutyBlocker,
} from "@/features/tracking/lib/duty-labels";
import {
  flushNativeTracking,
  getNativeDevice,
  onNativeStatus,
  onServerEndedDuty,
  openBatterySettings,
  openPhoneSettings,
  requestTrackingPermissions,
  startNativeTracking,
  stopNativeTracking,
  type TrackingPermissions,
  type TrackingStatus,
} from "@/features/tracking/native/tracking-bridge";
import { useIsNativeApp } from "@/features/tracking/native/use-native-app";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { clientEnv } from "@/lib/env/client";
import { formatNumber, formatRelativeTime, formatTime, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/tracking/components/duty-screen.tsx",
  dataId: "TRK-008",
});

/** The API as the native uploader must call it: absolute, on the page's own origin. */
function absoluteApiBase(): string {
  return new URL(clientEnv.apiBaseUrl, window.location.origin).toString().replace(/\/$/, "");
}

/**
 * TRK-008 · Duty, inside the Android app only: go on and off duty, and see that the route is being
 * recorded. Before duty can start, each missing permission is one card with a button to its
 * setting; the autostart advice for the phone's maker is help, not a blocker.
 */
export function DutyScreen(): React.JSX.Element {
  const native = useIsNativeApp();
  const config = useQuery(trackingConfigQueryOptions());

  if (!native) {
    return (
      <EmptyState
        icon={SmartPhone01Icon}
        level={2}
        title="Duty is in the Polysil app"
        description="Going on duty records your route, which only the Android app can do. Visits work here too."
        className="rounded-xl border border-dashed border-border"
      />
    );
  }
  if (config.isPending) return <DutySkeleton />;
  if (config.isError) {
    return <ErrorState error={config.error} onRetry={() => void config.refetch()} />;
  }
  if (!config.data.trackingAllowed) {
    return (
      <EmptyState
        icon={Location01Icon}
        level={2}
        title="Your role doesn't record a route"
        description="Duty is for field staff and their managers."
        className="rounded-xl border border-dashed border-border"
      />
    );
  }
  if (!config.data.consent.accepted) return <ConsentCard config={config.data} />;
  return <DutyPanel config={config.data} />;
}

function ConsentCard({ config }: { config: TrackingConfig }): React.JSX.Element {
  const consent = useAcceptConsent();
  const accept = useAsyncAction({
    action: () =>
      consent.mutateAsync({
        version: config.consent.requiredVersion,
        idempotencyKey: createRequestId(),
      }),
    logger: log,
    fn: "handleAcceptConsent",
    dataId: "TRK-008",
    onError: (error) => {
      toast.error("Consent not saved", { description: toUserFacingError(error).description });
    },
  });
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>Before you go on duty</CardTitle>
          <CardDescription>
            Read how your location is used while you&apos;re on duty.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm whitespace-pre-line text-foreground">{config.consent.text}</p>
        <Button
          size="lg"
          className="self-start"
          state={accept.state}
          loadingLabel="Saving…"
          successLabel="Accepted"
          errorLabel="Not saved"
          onClick={() => void accept.run()}
        >
          Accept
        </Button>
      </CardContent>
    </Card>
  );
}

function DutyPanel({ config }: { config: TrackingConfig }): React.JSX.Element {
  const queryClient = useQueryClient();
  const { data: session } = useSession();
  const status = useQuery(nativeStatusQueryOptions());
  const permissions = useQuery(nativePermissionsQueryOptions());
  const device = useQuery(nativeDeviceQueryOptions());
  const today = todayInIndia();
  const route = useQuery({
    ...routeQueryOptions(session?.user.id ?? "", today),
    enabled: session !== undefined,
  });
  const [ended, setEnded] = useState<string | null>(null);
  const start = useStartDuty();
  const end = useEndDuty();

  // Status changes and a duty the server ended arrive as events while the screen is open.
  useEffect(() => {
    const handles = [
      onNativeStatus((next) => {
        queryClient.setQueryData(nativeKeys.status(), next);
      }),
      onServerEndedDuty((next, reason) => {
        queryClient.setQueryData(nativeKeys.status(), next);
        setEnded(serverEndText(reason));
      }),
    ];
    return () => {
      for (const handle of handles) void handle.then((listener) => listener.remove());
    };
  }, [queryClient]);

  const goOnDuty = useAsyncAction({
    action: async (): Promise<TrackingStatus | undefined> => {
      setEnded(null);
      const fix = await getOneFix();
      const { deviceId } = await getNativeDevice();
      const body = {
        id: createRequestId(),
        device_id: deviceId,
        at: fix.at,
        sent_at: new Date().toISOString(),
        lat: fix.lat,
        lng: fix.lng,
        accuracy_m: fix.accuracyM,
      };
      // The API first, then the tracker with the id the server answered.
      const duty = await start.mutateAsync({ body, idempotencyKey: createRequestId() });
      await startNativeTracking({
        dutyId: duty.id,
        since: duty.startedAt,
        intervalSeconds: config.intervalSeconds,
        distanceFilterM: config.distanceFilterM,
        maxBatchPoints: config.maxBatchPoints,
        apiBaseUrl: absoluteApiBase(),
      });
      return queryClient.fetchQuery({ ...nativeStatusQueryOptions(), staleTime: 0 });
    },
    logger: log,
    fn: "handleGoOnDuty",
    dataId: "TRK-008",
    onSuccess: () => {
      toast.success("On duty", { description: "Your route is recorded until you go off duty." });
    },
    onError: (error) => {
      toast.error("Not on duty", { description: dutyErrorText(error) });
    },
  });

  const goOffDuty = useAsyncAction({
    action: async (): Promise<TrackingStatus | undefined> => {
      const current = status.data;
      // Send what waits first, then end the duty on the server, then stop the tracker.
      await flushNativeTracking().catch(() => undefined);
      if (current?.dutyId) {
        const fix = await getOneFix();
        await end.mutateAsync({
          body: {
            id: current.dutyId,
            at: fix.at,
            sent_at: new Date().toISOString(),
            lat: fix.lat,
            lng: fix.lng,
            accuracy_m: fix.accuracyM,
          },
          idempotencyKey: createRequestId(),
        });
      }
      await stopNativeTracking();
      return queryClient.fetchQuery({ ...nativeStatusQueryOptions(), staleTime: 0 });
    },
    logger: log,
    fn: "handleGoOffDuty",
    dataId: "TRK-008",
    onSuccess: () => {
      toast.success("Off duty", { description: "Your route is no longer recorded." });
    },
    onError: (error) => {
      toast.error("Still on duty", { description: dutyErrorText(error) });
    },
  });

  if (status.isPending || permissions.isPending) return <DutySkeleton />;
  if (status.isError || permissions.isError) {
    return (
      <ErrorState
        error={status.error ?? permissions.error}
        onRetry={() => {
          void status.refetch();
          void permissions.refetch();
        }}
      />
    );
  }

  const onDuty = status.data.onDuty;
  const blockers = dutyBlockers(permissions.data);
  const problem = uploadProblem(status.data.lastError);
  const autostart = autostartHelp(device.data?.manufacturer ?? "");
  const busy = goOnDuty.isBusy || goOffDuty.isBusy;

  return (
    <div className="flex flex-col gap-4">
      {ended === null ? null : <Notice tone="info">{ended}</Notice>}
      <Card>
        <CardContent className="flex flex-col items-center gap-4 py-6 text-center">
          <Button
            size="lg"
            variant={onDuty ? "outline" : "primary"}
            aria-pressed={onDuty}
            className="h-auto min-h-20 w-full max-w-xs text-lg"
            disabled={busy || (!onDuty && blockers.length > 0)}
            state={onDuty ? goOffDuty.state : goOnDuty.state}
            loadingLabel={onDuty ? "Going off duty…" : "Going on duty…"}
            successLabel={onDuty ? "On duty" : "Off duty"}
            errorLabel="Try again"
            onClick={() => void (onDuty ? goOffDuty.run() : goOnDuty.run())}
          >
            {onDuty ? "Go off duty" : "Go on duty"}
          </Button>
          <p className="text-sm text-muted-foreground">
            {onDuty && status.data.since
              ? `On duty since ${formatTime(status.data.since)}`
              : !onDuty && blockers.length > 0
                ? "Finish the steps below first."
                : "Off duty: your route isn't recorded."}
          </p>
        </CardContent>
      </Card>

      <dl aria-label="Duty today" className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Fact
          label="Last upload"
          value={
            status.data.lastUploadAt === null
              ? "Not yet"
              : formatRelativeTime(status.data.lastUploadAt)
          }
        />
        <Fact label="Points waiting" value={formatNumber(status.data.pendingPoints)} />
        <Fact
          label="Today"
          value={route.data === undefined ? "—" : `${formatNumber(route.data.distanceKm, 1)} km`}
        />
      </dl>

      {problem === null ? null : (
        <Notice tone={problem.tone === "calm" ? "info" : "warning"}>{problem.text}</Notice>
      )}

      {blockers.length === 0 ? null : (
        <section aria-label="Before duty can start" className="flex flex-col gap-3">
          {blockers.map((blocker) => (
            <BlockerCard
              key={blocker}
              blocker={blocker}
              permissions={permissions.data}
              onDone={() => {
                void queryClient.invalidateQueries({ queryKey: nativeKeys.permissions() });
              }}
            />
          ))}
        </section>
      )}

      {autostart === null ? null : (
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-0.5">
              <CardTitle level={3}>Allow autostart on your {autostart.brand}</CardTitle>
              <CardDescription>
                {autostart.brand} phones can stop apps in the background. Allow Polysil to start by
                itself, so your route has no gaps. The app can&apos;t check this for you.
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <a
              href={autostart.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline underline-offset-4"
            >
              How to allow it on {autostart.brand}
            </a>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-border bg-card p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-base font-semibold text-foreground tabular-nums">{value}</dd>
    </div>
  );
}

function BlockerCard({
  blocker,
  permissions,
  onDone,
}: {
  blocker: DutyBlocker;
  permissions: TrackingPermissions;
  onDone: () => void;
}): React.JSX.Element {
  const copy = BLOCKER_COPY[blocker];
  const fix = useAsyncAction({
    action: async (): Promise<void> => {
      if (blocker === "battery") return openBatterySettings();
      if (blocker === "gps") return openPhoneSettings("location");
      const state =
        blocker === "location"
          ? permissions.location
          : blocker === "background"
            ? permissions.background
            : permissions.notifications;
      // A permission refused for good is changed in the app's own settings page.
      if (state === "denied") return openPhoneSettings("app");
      await requestTrackingPermissions();
    },
    logger: log,
    fn: "handleFixDutyBlocker",
    dataId: "TRK-008",
    onSuccess: onDone,
  });
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>{copy.title}</CardTitle>
          <CardDescription>{copy.body}</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <Button variant="outline" size="lg" state={fix.state} onClick={() => void fix.run()}>
          {copy.action}
        </Button>
      </CardContent>
    </Card>
  );
}

/** Why going on or off duty failed, in words. */
function dutyErrorText(error: unknown): string {
  if (error instanceof Error && error.message === "denied") {
    return "Location isn't allowed. Allow it, then try again.";
  }
  if (error instanceof Error && (error.message === "failed" || error.message === "unavailable")) {
    return "The phone couldn't find where you are. Move to open sky and try again.";
  }
  if (isApiError(error) && error.code === "consent_required") {
    return "Accept the tracking consent first.";
  }
  return toUserFacingError(error).description;
}

export function DutySkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading duty" className="flex flex-col gap-4">
      <Skeleton className="h-36 w-full rounded-xl" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    </div>
  );
}
