"use client";

import {
  Add01Icon,
  ArrowRight01Icon,
  ComputerIcon,
  CustomerSupportIcon,
  HelpCircleIcon,
  Invoice03Icon,
  Moon02Icon,
  PackageIcon,
  Sun03Icon,
  UserAccountIcon,
  UserMultiple02Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";
import { Icon, type IconGlyph } from "@/components/ui/icon";
import { assistantSearchQueryOptions } from "@/features/assistant/api/assistant.queries";
import {
  ASSISTANT_QUERY_MAX,
  RECORD_SEARCH_MIN,
  type AssistantAction,
  type AssistantRecord,
  type RecordKind,
} from "@/features/assistant/api/assistant.schemas";
import { openScreen, RECORD_KIND_LABELS } from "@/features/assistant/lib/assistant-routes";
import { useSession } from "@/features/session/hooks/use-session";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useTheme } from "@/lib/theme/use-theme";

import { visibleNavSections } from "./navigation";
import { useNavGates } from "./use-nav-gates";

export interface CommandMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** The backend asks for a 250 ms pause before a search goes out (in-app-assistant.md). */
const SEARCH_DEBOUNCE_MS = 250;

const RECORD_ICONS: Readonly<Record<RecordKind, IconGlyph>> = {
  lead: UserMultiple02Icon,
  customer: UserAccountIcon,
  quotation: Invoice03Icon,
  sales_order: PackageIcon,
  complaint: CustomerSupportIcon,
};

/**
 * ⌘K / Ctrl+K (or "/") — BOT-001. Jump to a page, take an action the backend says the user may
 * take, or open a record found by number, mobile or name (from 3 characters). Pages filter here;
 * actions and records come from the server, so each carries what was typed as a keyword and
 * cmdk keeps it. No open/close animation: it is a keyboard tool used many times a day.
 */
export function CommandMenu({ open, onOpenChange }: CommandMenuProps): React.JSX.Element {
  const router = useRouter();
  const { data: session } = useSession();
  const gates = useNavGates();
  const { setPreference } = useTheme();
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);

  const answer = useQuery({
    ...assistantSearchQueryOptions(term),
    enabled: open && session !== undefined,
  });
  const actions = answer.data?.actions ?? [];
  const records = term.length >= RECORD_SEARCH_MIN ? (answer.data?.records ?? []) : [];
  const typed = search.trim();
  const waiting = typed !== term || answer.isFetching;

  const pages = session
    ? visibleNavSections(session.permissions, session.userType, undefined, gates)
        .flatMap((section) => section.items)
        .filter((item) => item.href !== undefined)
    : [];

  const changeOpen = (next: boolean): void => {
    if (!next) setSearch("");
    onOpenChange(next);
  };

  const run = (action: () => void): void => {
    changeOpen(false);
    action();
  };

  return (
    <CommandDialog
      open={open}
      onOpenChange={changeOpen}
      description="Search for a page, an action, or a lead, customer, quotation, order or complaint"
    >
      <Command loop>
        <CommandInput
          value={search}
          onValueChange={setSearch}
          maxLength={ASSISTANT_QUERY_MAX}
          placeholder="Search pages, actions and records…"
          aria-label="Search pages, actions and records"
        />
        <CommandList>
          <CommandEmpty>
            {waiting ? "Searching…" : "Nothing matches. Try a number, a mobile or a name."}
          </CommandEmpty>
          {actions.length > 0 ? (
            <CommandGroup heading="Actions">
              {actions.map((action) => (
                <ActionItem
                  key={action.key}
                  action={action}
                  search={typed}
                  onSelect={() => {
                    run(() => {
                      openScreen(router, action.screen);
                    });
                  }}
                />
              ))}
            </CommandGroup>
          ) : null}
          {records.length > 0 ? (
            <CommandGroup heading="Records">
              {records.map((record) => (
                <RecordItem
                  key={`${record.kind}:${record.id}`}
                  record={record}
                  search={typed}
                  onSelect={() => {
                    run(() => {
                      openScreen(router, record.screen, record.id);
                    });
                  }}
                />
              ))}
            </CommandGroup>
          ) : null}
          {answer.isError && typed.length >= RECORD_SEARCH_MIN ? (
            <p role="status" className="px-2 py-1.5 text-xs text-muted-foreground">
              Couldn&apos;t search records just now. Pages still work.
            </p>
          ) : null}
          {pages.length > 0 ? (
            <CommandGroup heading="Go to">
              {pages.map((item) => (
                <CommandItem
                  key={item.id}
                  value={`page:${item.label}`}
                  keywords={[item.label]}
                  onSelect={() => {
                    run(() => {
                      if (item.href !== undefined) {
                        router.push(item.href);
                      }
                    });
                  }}
                >
                  <Icon icon={item.icon} />
                  {item.label}
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          <CommandGroup heading="Preferences">
            <CommandItem
              value="Switch to light theme"
              onSelect={() => {
                run(() => {
                  setPreference("light");
                });
              }}
            >
              <Icon icon={Sun03Icon} />
              Switch to light theme
            </CommandItem>
            <CommandItem
              value="Switch to dark theme"
              onSelect={() => {
                run(() => {
                  setPreference("dark");
                });
              }}
            >
              <Icon icon={Moon02Icon} />
              Switch to dark theme
            </CommandItem>
            <CommandItem
              value="Use system theme"
              onSelect={() => {
                run(() => {
                  setPreference("system");
                });
              }}
            >
              <Icon icon={ComputerIcon} />
              Use system theme
            </CommandItem>
            <CommandItem
              value="Help: everything you can do here"
              keywords={["help", "what can I do", "shortcuts"]}
              onSelect={() => {
                run(() => {
                  router.push("/help");
                });
              }}
            >
              <Icon icon={HelpCircleIcon} />
              Help: everything you can do here
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}

interface ActionItemProps {
  action: AssistantAction;
  /** What was typed: the server already matched it, so cmdk must keep the item. */
  search: string;
  onSelect: () => void;
}

function ActionItem({ action, search, onSelect }: ActionItemProps): React.JSX.Element {
  const starts = action.screen.endsWith(".new");
  return (
    <CommandItem
      value={`action:${action.key}`}
      keywords={[search, action.title, action.hint]}
      onSelect={onSelect}
    >
      <Icon icon={starts ? Add01Icon : ArrowRight01Icon} />
      <span className="flex min-w-0 flex-col">
        <span className="truncate">{action.title}</span>
        <span className="truncate text-xs text-muted-foreground">{action.hint}</span>
      </span>
    </CommandItem>
  );
}

interface RecordItemProps {
  record: AssistantRecord;
  search: string;
  onSelect: () => void;
}

function RecordItem({ record, search, onSelect }: RecordItemProps): React.JSX.Element {
  const kind = RECORD_KIND_LABELS[record.kind];
  return (
    <CommandItem
      value={`record:${record.kind}:${record.id}`}
      keywords={[search, record.label]}
      onSelect={onSelect}
    >
      <Icon icon={RECORD_ICONS[record.kind]} />
      <span className="min-w-0 truncate">{record.label}</span>
      <CommandShortcut className="shrink-0 whitespace-nowrap text-muted-foreground">
        {kind}
      </CommandShortcut>
    </CommandItem>
  );
}
