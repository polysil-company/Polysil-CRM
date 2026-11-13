import { cva, type VariantProps } from "class-variance-authority";

/**
 * Button styles, based on shadcn/ui (base-nova) and restyled to Polysil tokens.
 *
 * A plain module (no "use client"), so Server Components can style links as
 * buttons: <Link href="/leads" className={buttonVariants({ variant: "outline" })}>.
 */
export const buttonVariants = cva(
  [
    "group/button relative inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-transparent font-medium whitespace-nowrap select-none",
    "disabled:cursor-not-allowed disabled:opacity-50 data-disabled:cursor-not-allowed data-disabled:opacity-50",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        primary: "press-scale bg-primary text-primary-foreground shadow-xs hover:bg-primary-hover",
        secondary: "press-scale bg-secondary text-secondary-foreground hover:bg-secondary-hover",
        outline:
          "press-scale border-border bg-card text-foreground shadow-xs hover:border-border-strong hover:bg-accent aria-expanded:bg-accent",
        ghost:
          "press-scale text-muted-foreground hover:bg-accent hover:text-foreground aria-expanded:bg-accent aria-expanded:text-foreground",
        destructive:
          "press-scale bg-destructive text-destructive-foreground shadow-xs hover:bg-destructive-hover",
        link: "text-primary-text underline-offset-4 transition-colors hover:underline",
      },
      size: {
        xs: "h-control-xs px-2 text-xs [&_svg]:size-3.5",
        sm: "h-control-sm px-2.5 text-sm [&_svg]:size-4",
        md: "h-control-md px-3.5 text-sm [&_svg]:size-4",
        lg: "h-control-lg px-5 text-base [&_svg]:size-4.5",
        "icon-xs": "size-control-xs after:absolute after:-inset-1.5 [&_svg]:size-3.5",
        "icon-sm": "size-control-sm after:absolute after:-inset-1 [&_svg]:size-4",
        "icon-md": "size-control-md [&_svg]:size-4",
        "icon-lg": "size-control-lg [&_svg]:size-5",
      },
    },
    compoundVariants: [{ variant: "link", className: "h-auto px-0" }],
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export type ButtonVariantProps = VariantProps<typeof buttonVariants>;
