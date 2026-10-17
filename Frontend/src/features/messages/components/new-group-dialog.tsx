"use client";

import { UserGroupIcon } from "@hugeicons/core-free-icons";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { useCreateGroup } from "@/features/messages/api/messages.mutations";
import {
  GROUP_MAX_MEMBERS,
  GROUP_NAME_MAX_LENGTH,
  type Person,
} from "@/features/messages/api/messages.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

import { PeoplePicker } from "./people-picker";

const log = createLogger({
  file: "features/messages/components/new-group-dialog.tsx",
  dataId: "MSG-006",
});

interface Problems {
  readonly name?: string;
  readonly members?: string;
}

/** What is missing before the group can be made, in the form's words. */
export function groupProblems(name: string, members: readonly Person[]): Problems {
  return {
    ...(name.trim() === "" ? { name: "Name the group." } : {}),
    ...(members.length === 0 ? { members: "Choose at least one colleague." } : {}),
  };
}

/**
 * MSG-006 · "New group": a name and the colleagues in it, from the staff directory. The user
 * is added and manages it; the group opens straight away, listed before anyone writes.
 */
export function NewGroupDialog(): React.JSX.Element {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [members, setMembers] = useState<readonly Person[]>([]);
  const [problems, setProblems] = useState<Problems>({});
  const create = useCreateGroup();

  const reset = (): void => {
    setName("");
    setMembers([]);
    setProblems({});
  };

  const submit = useAsyncAction({
    action: () =>
      create.mutateAsync({ name: name.trim(), member_ids: members.map((person) => person.id) }),
    logger: log,
    fn: "handleCreateGroup",
    dataId: "MSG-006",
    onSuccess: (group) => {
      toast.success("Group made", { description: name.trim() });
      setOpen(false);
      reset();
      router.push(`/messages/${encodeURIComponent(group.id)}`);
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      if (fields.name !== undefined || fields.member_ids !== undefined) {
        setProblems({
          ...(fields.name === undefined ? {} : { name: fields.name }),
          ...(fields.member_ids === undefined
            ? {}
            : { members: "Someone chosen can't be added. Choose again." }),
        });
        return;
      }
      toast.error("Group not made", { description: toUserFacingError(error).description });
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      {/* Icon only: the list's header is narrow beside the thread. Named for screen readers. */}
      <DialogTrigger
        render={
          <Button variant="outline" size="icon-sm" aria-label="New group" title="New group" />
        }
      >
        <Icon icon={UserGroupIcon} />
      </DialogTrigger>
      <DialogContent size="sm">
        <form
          noValidate
          aria-label="New group"
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            event.preventDefault();
            const found = groupProblems(name, members);
            setProblems(found);
            if (found.name === undefined && found.members === undefined) {
              void submit.run();
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>New group</DialogTitle>
            <DialogDescription>
              Name it and choose who is in it. You manage the group: you can rename it and remove
              people.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="flex flex-col gap-4">
            <Field data-invalid={problems.name === undefined ? undefined : true}>
              <FieldLabel htmlFor="group-name">Group name</FieldLabel>
              <Input
                id="group-name"
                value={name}
                maxLength={GROUP_NAME_MAX_LENGTH}
                autoComplete="off"
                aria-invalid={problems.name === undefined ? undefined : true}
                aria-describedby={problems.name === undefined ? undefined : "group-name-error"}
                onChange={(event) => {
                  setName(event.target.value);
                }}
              />
              <FieldError id="group-name-error">{problems.name}</FieldError>
            </Field>
            <fieldset className="flex flex-col gap-1.5">
              <legend className="mb-1.5 text-sm font-medium text-foreground">Members</legend>
              <FieldDescription>
                Up to {GROUP_MAX_MEMBERS - 1} colleagues, besides you.
              </FieldDescription>
              {problems.members === undefined ? null : (
                <p role="alert" className="text-sm text-danger">
                  {problems.members}
                </p>
              )}
              <PeoplePicker
                chosen={members}
                onChange={setMembers}
                limit={GROUP_MAX_MEMBERS - 1}
                enabled={open}
              />
            </fieldset>
          </DialogBody>
          <DialogFooter>
            <DialogClose
              render={<Button type="button" variant="outline" disabled={submit.isBusy} />}
            >
              Cancel
            </DialogClose>
            <Button
              type="submit"
              state={submit.state}
              loadingLabel="Making…"
              successLabel="Made"
              errorLabel="Not made"
            >
              Make the group
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
