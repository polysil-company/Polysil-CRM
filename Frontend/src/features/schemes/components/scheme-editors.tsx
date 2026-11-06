"use client";

import { useQuery } from "@tanstack/react-query";
import { notFound } from "next/navigation";
import type * as React from "react";

import { AccessDenied } from "@/components/patterns/access-denied";
import { QueryView } from "@/components/patterns/query-view";
import { Skeleton } from "@/components/ui/skeleton";
import { schemeDetailQueryOptions } from "@/features/schemes/api/schemes.queries";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { isApiError } from "@/lib/api/errors";

import { SchemeForm } from "./scheme-form";

/** SCHM-002 · New scheme, for those who may create one. */
export function NewScheme(): React.JSX.Element {
  const session = useSession();
  const canCreate = useCan("schemes", "create");
  if (session.isPending) return <Skeleton className="h-96 w-full rounded-xl" />;
  return canCreate ? <SchemeForm scheme={null} /> : <AccessDenied />;
}

/** SCHM-002 · Change a scheme, for those who may edit schemes. */
export function EditScheme({ schemeId }: { schemeId: string }): React.JSX.Element {
  const session = useSession();
  const canEdit = useCan("schemes", "edit");
  const query = useQuery({ ...schemeDetailQueryOptions(schemeId), enabled: canEdit });
  if (isApiError(query.error) && query.error.status === 404) notFound();
  if (session.isPending) return <Skeleton className="h-96 w-full rounded-xl" />;
  if (!canEdit) return <AccessDenied />;
  return (
    <QueryView
      query={query}
      pending={<Skeleton className="h-96 w-full rounded-xl" />}
      isEmpty={() => false}
      empty={null}
    >
      {(scheme) => <SchemeForm scheme={scheme} />}
    </QueryView>
  );
}
