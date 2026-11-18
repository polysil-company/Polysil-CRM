"use client";

import { Cancel01Icon, Search01Icon } from "@hugeicons/core-free-icons";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { cn } from "@/lib/utils";

export interface SearchFieldProps {
  /** Accessible name, e.g. "Search leads". */
  label: string;
  /** The applied search (usually from the URL). Shown whenever the field is not being edited. */
  value: string;
  placeholder?: string;
  /** Called with the trimmed value after typing pauses, on Enter, on blur and when cleared. */
  onSearch: (value: string) => void;
  debounceMs?: number;
  className?: string;
}

/**
 * Search input that waits for a pause in typing before searching, so each
 * keystroke doesn't hit the API. Escape clears it. While not focused it always
 * shows the applied value, so "Reset filters" or the back button stay in sync.
 */
export function SearchField({
  label,
  value,
  placeholder,
  onSearch,
  debounceMs = 300,
  className,
}: SearchFieldProps): React.JSX.Element {
  const [draft, setDraft] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const shown = draft ?? value;

  useEffect(() => {
    return () => {
      clearTimeout(timer.current);
    };
  }, []);

  const commit = (next: string): void => {
    clearTimeout(timer.current);
    if (next.trim() !== value) {
      onSearch(next.trim());
    }
  };

  const schedule = (next: string): void => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      onSearch(next.trim());
    }, debounceMs);
  };

  const clear = (): void => {
    setDraft(null);
    commit("");
  };

  return (
    <InputGroup className={cn("md:w-72", className)}>
      <InputGroupAddon>
        <Icon icon={Search01Icon} />
      </InputGroupAddon>
      <InputGroupInput
        type="search"
        value={shown}
        aria-label={label}
        placeholder={placeholder}
        autoComplete="off"
        className="[&::-webkit-search-cancel-button]:hidden"
        onFocus={() => {
          setDraft(value);
        }}
        onBlur={() => {
          if (draft !== null) {
            commit(draft);
          }
          setDraft(null);
        }}
        onChange={(event) => {
          setDraft(event.target.value);
          schedule(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit(shown);
          }
          if (event.key === "Escape" && shown !== "") {
            event.preventDefault();
            setDraft("");
            commit("");
          }
        }}
      />
      {shown === "" ? null : (
        <InputGroupAddon align="end">
          <Button variant="ghost" size="icon-xs" aria-label="Clear search" onClick={clear}>
            <Icon icon={Cancel01Icon} />
          </Button>
        </InputGroupAddon>
      )}
    </InputGroup>
  );
}
