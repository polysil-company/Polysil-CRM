import type * as React from "react";

import { Avatar, AvatarFallback, AvatarImage, getInitials } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

export interface AvatarLabelProps {
  name: string;
  secondary?: string | undefined;
  imageUrl?: string | null | undefined;
  size?: "xs" | "sm" | "md";
  className?: string;
}

/** Person or business: avatar, name and an optional secondary line. */
export function AvatarLabel({
  name,
  secondary,
  imageUrl,
  size = "sm",
  className,
}: AvatarLabelProps): React.JSX.Element {
  return (
    <span className={cn("flex min-w-0 items-center gap-2", className)}>
      <Avatar size={size}>
        {imageUrl ? <AvatarImage src={imageUrl} alt="" /> : null}
        <AvatarFallback>{getInitials(name)}</AvatarFallback>
      </Avatar>
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-medium text-foreground">{name}</span>
        {secondary ? (
          <span className="truncate text-xs text-muted-foreground">{secondary}</span>
        ) : null}
      </span>
    </span>
  );
}
