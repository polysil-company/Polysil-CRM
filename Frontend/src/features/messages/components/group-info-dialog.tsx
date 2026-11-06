"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { QueryView } from "@/components/patterns/query-view";
import { Avatar, AvatarFallback, getInitials } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAddMembers,
  useRemoveMember,
  useRenameGroup,
} from "@/features/messages/api/messages.mutations";
import { groupMembersQueryOptions } from "@/features/messages/api/messages.queries";
import {
  GROUP_MAX_MEMBERS,
  GROUP_NAME_MAX_LENGTH,
  type GroupConversation,
  type Member,
  type Person,
} from "@/features/messages/api/messages.schemas";
import { describePerson } from "@/features/messages/lib/format-messages";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { PeoplePicker } from "./people-picker";

const log = createLogger({
  file: "features/messages/components/group-info-dialog.tsx",
  dataId: "MSG-006",
});

/** "4 members". */
export function memberCountLabel(count: number): string {
  return `${formatNumber(count)} ${count === 1 ? "member" : "members"}`;
}

export interface GroupInfoDialogProps {
  conversation: GroupConversation;
  myId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The user has left the group: the page moves away from it. */
  onLeft: () => void;
}

/**
 * MSG-006 · Group info: who is in it (and who has left), add people, and leave. The manager
 * also renames the group and removes people. "Manages this group" follows `is_manager`, not
 * who made it: when the manager leaves, the longest-standing member takes over.
 */
export function GroupInfoDialog({
  conversation,
  myId,
  open,
  onOpenChange,
  onLeft,
}: GroupInfoDialogProps): React.JSX.Element {
  const members = useQuery({ ...groupMembersQueryOptions(conversation.id), enabled: open });
  const { group } = conversation;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Group info</DialogTitle>
          <DialogDescription>
            {group.name} · {memberCountLabel(group.memberCount)}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-5 pb-5">
          {group.iManage ? <RenameGroup conversation={conversation} /> : null}
          <QueryView
            query={members}
            pending={<MembersSkeleton />}
            isEmpty={(list) => list.length === 0}
            empty={<p className="text-sm text-muted-foreground">No one is in this group.</p>}
          >
            {(list) => (
              <MemberSections
                conversation={conversation}
                members={list}
                myId={myId}
                onLeft={onLeft}
              />
            )}
          </QueryView>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

function RenameGroup({ conversation }: { conversation: GroupConversation }): React.JSX.Element {
  const [name, setName] = useState(conversation.group.name);
  const [problem, setProblem] = useState<string | null>(null);
  const rename = useRenameGroup(conversation.id);
  const changed = name.trim() !== "" && name.trim() !== conversation.group.name;

  const save = useAsyncAction({
    action: () => rename.mutateAsync(name.trim()),
    logger: log,
    fn: "handleRenameGroup",
    dataId: "MSG-006",
    onSuccess: (renamed) => {
      toast.success("Group renamed", {
        description: renamed.kind === "group" ? renamed.group.name : undefined,
      });
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      setProblem(fields.name ?? toUserFacingError(error).title);
    },
  });

  return (
    <form
      noValidate
      aria-label="Rename the group"
      className="flex items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim() === "") {
          setProblem("Name the group.");
          return;
        }
        setProblem(null);
        void save.run();
      }}
    >
      <Field className="flex-1" data-invalid={problem === null ? undefined : true}>
        <FieldLabel htmlFor="group-rename">Group name</FieldLabel>
        <Input
          id="group-rename"
          value={name}
          maxLength={GROUP_NAME_MAX_LENGTH}
          autoComplete="off"
          aria-invalid={problem === null ? undefined : true}
          aria-describedby={problem === null ? undefined : "group-rename-error"}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
        <FieldError id="group-rename-error">{problem}</FieldError>
      </Field>
      <Button
        type="submit"
        variant="outline"
        disabled={!changed}
        state={save.state}
        loadingLabel="Saving…"
        successLabel="Saved"
        errorLabel="Not saved"
      >
        Rename
      </Button>
    </form>
  );
}

function MemberSections({
  conversation,
  members,
  myId,
  onLeft,
}: {
  conversation: GroupConversation;
  members: readonly Member[];
  myId: string | null;
  onLeft: () => void;
}): React.JSX.Element {
  const current = members.filter((member) => member.leftAt === null);
  const former = members.filter((member) => member.leftAt !== null);

  return (
    <>
      <section aria-labelledby="group-members-heading" className="flex flex-col gap-2">
        <h3 id="group-members-heading" className="text-sm font-medium text-foreground">
          Members
        </h3>
        <ul className="flex flex-col gap-0.5">
          {current.map((member) => (
            <MemberRow
              key={member.person.id}
              conversation={conversation}
              member={member}
              me={member.person.id === myId}
            />
          ))}
        </ul>
      </section>
      <AddPeople conversation={conversation} current={current} />
      {former.length === 0 ? null : (
        <section aria-labelledby="group-former-heading" className="flex flex-col gap-1">
          <h3 id="group-former-heading" className="text-sm font-medium text-foreground">
            Left the group
          </h3>
          <p className="text-xs text-muted-foreground">
            {former.map((member) => member.person.name).join(", ")}
          </p>
        </section>
      )}
      {myId === null ? null : (
        <LeaveGroup conversation={conversation} myId={myId} onLeft={onLeft} />
      )}
    </>
  );
}

function MemberRow({
  conversation,
  member,
  me,
}: {
  conversation: GroupConversation;
  member: Member;
  me: boolean;
}): React.JSX.Element {
  const remove = useRemoveMember(conversation.id);
  const { person } = member;

  const run = useAsyncAction({
    action: () => remove.mutateAsync(person.id),
    logger: log,
    fn: "handleRemoveMember",
    dataId: "MSG-006",
    onSuccess: () => {
      toast.success(`${person.name} removed`, { description: conversation.group.name });
    },
    onError: (error) => {
      toast.error(`${person.name} not removed`, {
        description: toUserFacingError(error).description,
      });
    },
  });

  return (
    <li className="flex items-center gap-3 rounded-lg p-2">
      <Avatar size="md">
        <AvatarFallback>{getInitials(person.name)}</AvatarFallback>
      </Avatar>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-sm font-medium text-foreground">
          {person.name}
          {me ? <span className="font-normal text-muted-foreground"> (you)</span> : null}
        </span>
        <span className="truncate text-xs text-muted-foreground">{describePerson(person)}</span>
      </span>
      {member.isManager ? (
        <Badge size="sm" variant="primary" className="shrink-0">
          Manages this group
        </Badge>
      ) : null}
      {conversation.group.iManage && !me ? (
        <Button
          variant="ghost"
          size="sm"
          aria-label={`Remove ${person.name}`}
          state={run.state}
          loadingLabel="Removing…"
          successLabel="Removed"
          errorLabel="Not removed"
          onClick={() => {
            void run.run();
          }}
        >
          Remove
        </Button>
      ) : null}
    </li>
  );
}

function AddPeople({
  conversation,
  current,
}: {
  conversation: GroupConversation;
  current: readonly Member[];
}): React.JSX.Element {
  const [adding, setAdding] = useState(false);
  const [chosen, setChosen] = useState<readonly Person[]>([]);
  const add = useAddMembers(conversation.id);
  const room = Math.max(0, GROUP_MAX_MEMBERS - current.length);
  const inGroup = new Set(current.map((member) => member.person.id));

  const save = useAsyncAction({
    action: () => add.mutateAsync(chosen.map((person) => person.id)),
    logger: log,
    fn: "handleAddMembers",
    dataId: "MSG-006",
    onSuccess: () => {
      toast.success(
        chosen.length === 1 ? "1 colleague added" : `${String(chosen.length)} colleagues added`,
        {
          description: conversation.group.name,
        },
      );
      setChosen([]);
      setAdding(false);
    },
    onError: (error) => {
      toast.error("No one added", {
        description:
          isApiError(error) && error.code === "group_full"
            ? `A group takes ${String(GROUP_MAX_MEMBERS)} people. Choose fewer.`
            : toUserFacingError(error).description,
      });
    },
  });

  if (!adding) {
    return (
      <Button
        variant="outline"
        size="sm"
        className="self-start"
        disabled={room === 0}
        onClick={() => {
          setAdding(true);
        }}
      >
        {room === 0 ? "The group is full" : "Add people"}
      </Button>
    );
  }

  return (
    <section
      aria-label="Add people"
      className="flex flex-col gap-2 rounded-lg border border-border p-3"
    >
      <PeoplePicker
        chosen={chosen}
        onChange={setChosen}
        excludeIds={inGroup}
        limit={room}
        enabled={adding}
      />
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={save.isBusy}
          onClick={() => {
            setChosen([]);
            setAdding(false);
          }}
        >
          Cancel
        </Button>
        <Button
          size="sm"
          disabled={chosen.length === 0}
          state={save.state}
          loadingLabel="Adding…"
          successLabel="Added"
          errorLabel="Not added"
          onClick={() => {
            void save.run();
          }}
        >
          {chosen.length === 0 ? "Add" : `Add ${String(chosen.length)}`}
        </Button>
      </div>
    </section>
  );
}

function LeaveGroup({
  conversation,
  myId,
  onLeft,
}: {
  conversation: GroupConversation;
  myId: string;
  onLeft: () => void;
}): React.JSX.Element {
  const [confirming, setConfirming] = useState(false);
  const remove = useRemoveMember(conversation.id);

  const leave = useAsyncAction({
    action: () => remove.mutateAsync(myId),
    logger: log,
    fn: "handleLeaveGroup",
    dataId: "MSG-006",
    onSuccess: () => {
      toast.success("You left the group", { description: conversation.group.name });
      onLeft();
    },
    onError: (error) => {
      toast.error("You're still in the group", {
        description: toUserFacingError(error).description,
      });
    },
  });

  if (!confirming) {
    return (
      <Button
        variant="outline"
        size="sm"
        className="self-start text-danger"
        onClick={() => {
          setConfirming(true);
        }}
      >
        Leave the group
      </Button>
    );
  }

  return (
    <div
      role="group"
      aria-label="Leave the group"
      className="flex flex-col gap-2 rounded-lg border border-border p-3"
    >
      <p className="text-sm text-foreground">
        Leave {conversation.group.name}? It disappears for you, messages included. Someone in it can
        add you back.
      </p>
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={leave.isBusy}
          onClick={() => {
            setConfirming(false);
          }}
        >
          Stay
        </Button>
        <Button
          variant="destructive"
          size="sm"
          state={leave.state}
          loadingLabel="Leaving…"
          successLabel="Left"
          errorLabel="Not left"
          onClick={() => {
            void leave.run();
          }}
        >
          Leave
        </Button>
      </div>
    </div>
  );
}

function MembersSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading members" className="flex flex-col gap-0.5">
      {[0, 1, 2].map((row) => (
        <div key={row} className="flex items-center gap-3 p-2">
          <Skeleton className="size-8 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3.5 w-32" />
            <Skeleton className="h-3 w-44" />
          </div>
        </div>
      ))}
    </div>
  );
}
