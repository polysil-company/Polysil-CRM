import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Living reference for src/styles/tokens.css — the one design source.
 * Every swatch, size, shadow and curve below is a class generated from that
 * file, so a token change shows up here, in the app and in the docs at once.
 * Switch the theme in the toolbar to review dark mode.
 */

interface TokenSample {
  readonly name: string;
  readonly className: string;
}

interface ColourGroup {
  readonly title: string;
  readonly description: string;
  readonly tokens: readonly TokenSample[];
}

const COLOUR_GROUPS: readonly ColourGroup[] = [
  {
    title: "Surfaces",
    description: "Layers from the page ground up to floating menus.",
    tokens: [
      { name: "background", className: "bg-background" },
      { name: "panel", className: "bg-panel" },
      { name: "card", className: "bg-card" },
      { name: "popover", className: "bg-popover" },
      { name: "sidebar", className: "bg-sidebar" },
      { name: "overlay", className: "bg-overlay" },
    ],
  },
  {
    title: "Text",
    description: "Three steps of emphasis. Anything people must read uses foreground or muted.",
    tokens: [
      { name: "foreground", className: "bg-foreground" },
      { name: "muted-foreground", className: "bg-muted-foreground" },
      { name: "subtle-foreground", className: "bg-subtle-foreground" },
    ],
  },
  {
    title: "Interaction fills",
    description: "Translucent, so hover and pressed states work on every surface.",
    tokens: [
      { name: "muted", className: "bg-muted" },
      { name: "accent", className: "bg-accent" },
      { name: "accent-strong", className: "bg-accent-strong" },
    ],
  },
  {
    title: "Actions",
    description: "Teal — water — is the one action colour.",
    tokens: [
      { name: "primary", className: "bg-primary" },
      { name: "primary-hover", className: "bg-primary-hover" },
      { name: "primary-soft", className: "bg-primary-soft" },
      { name: "secondary", className: "bg-secondary" },
      { name: "destructive", className: "bg-destructive" },
    ],
  },
  {
    title: "Selection",
    description: "Sun yellow marks what the user picked: checked boxes and selected rows.",
    tokens: [
      { name: "highlight", className: "bg-highlight" },
      { name: "highlight-soft", className: "bg-highlight-soft" },
      { name: "row-selected", className: "bg-row-selected" },
    ],
  },
  {
    title: "Status",
    description: "Meaning, never decoration. Always paired with text or an icon.",
    tokens: [
      { name: "success", className: "bg-success" },
      { name: "success-soft", className: "bg-success-soft" },
      { name: "warning", className: "bg-warning" },
      { name: "warning-soft", className: "bg-warning-soft" },
      { name: "danger", className: "bg-danger" },
      { name: "danger-soft", className: "bg-danger-soft" },
      { name: "info", className: "bg-info" },
      { name: "info-soft", className: "bg-info-soft" },
    ],
  },
  {
    title: "Lines",
    description: "Hairlines for structure, stronger lines for controls, ring for focus.",
    tokens: [
      { name: "border", className: "bg-border" },
      { name: "border-strong", className: "bg-border-strong" },
      { name: "input", className: "bg-input" },
      { name: "control", className: "bg-control" },
      { name: "ring", className: "bg-ring" },
    ],
  },
  {
    title: "Tags",
    description:
      "Categorical dots. A label always gets the same colour — a crop looks the same everywhere.",
    tokens: [
      { name: "tag-teal", className: "bg-tag-teal" },
      { name: "tag-blue", className: "bg-tag-blue" },
      { name: "tag-violet", className: "bg-tag-violet" },
      { name: "tag-rose", className: "bg-tag-rose" },
      { name: "tag-orange", className: "bg-tag-orange" },
      { name: "tag-amber", className: "bg-tag-amber" },
      { name: "tag-lime", className: "bg-tag-lime" },
      { name: "tag-slate", className: "bg-tag-slate" },
    ],
  },
  {
    title: "Charts",
    description: "Series colours, in order.",
    tokens: [
      { name: "chart-1", className: "bg-chart-1" },
      { name: "chart-2", className: "bg-chart-2" },
      { name: "chart-3", className: "bg-chart-3" },
      { name: "chart-4", className: "bg-chart-4" },
      { name: "chart-5", className: "bg-chart-5" },
    ],
  },
];

const TYPE_SCALE = [
  { className: "text-4xl", size: 48, use: "Public site hero" },
  { className: "text-3xl", size: 36, use: "Public site headings" },
  { className: "text-2xl", size: 28, use: "KPI values" },
  { className: "text-xl", size: 22, use: "Page titles" },
  { className: "text-lg", size: 18, use: "Card and section titles" },
  { className: "text-md", size: 16, use: "Inputs on touch screens" },
  { className: "text-base", size: 14, use: "Body" },
  { className: "text-sm", size: 13, use: "Table cells, navigation, buttons, inputs" },
  { className: "text-xs", size: 12, use: "Captions, table headers, meta" },
  { className: "text-2xs", size: 11, use: "Counts and overlines" },
] as const;

const RADII = [
  { className: "rounded-xs", use: "Checkbox, kbd" },
  { className: "rounded-sm", use: "Badges, tags, tooltips" },
  { className: "rounded-md", use: "Buttons, inputs, menu items" },
  { className: "rounded-lg", use: "Menus and popovers" },
  { className: "rounded-xl", use: "Cards and dialogs" },
  { className: "rounded-2xl", use: "Main panel and sheets" },
  { className: "rounded-3xl", use: "Marketing surfaces" },
  { className: "rounded-full", use: "Avatars, pills, dots" },
] as const;

const SHADOWS = [
  { className: "shadow-xs", use: "Resting surfaces: cards, inputs, buttons" },
  { className: "shadow-sm", use: "Slightly raised" },
  { className: "shadow-md", use: "Floating: tooltips and menus" },
  { className: "shadow-lg", use: "Overlays: dialogs, sheets, the selection bar" },
  { className: "shadow-panel", use: "The inset main panel" },
] as const;

const DURATIONS = [
  { className: "duration-instant", ms: 0, use: "Keyboard-driven UI; tooltips after the first" },
  { className: "duration-press", ms: 120, use: "Press feedback" },
  { className: "duration-fast", ms: 150, use: "Hover, checkbox, tooltip" },
  { className: "duration-base", ms: 200, use: "Menus, tabs, state crossfades" },
  { className: "duration-slow", ms: 300, use: "Dialogs, sheets, overlays" },
] as const;

const EASINGS = [
  { className: "ease-out", use: "Entering, and responding to input" },
  { className: "ease-in-out", use: "Moving on screen — the tab indicator" },
  { className: "ease-drawer", use: "Sheets and the phone bottom sheet" },
] as const;

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-col gap-0.5">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      {children}
    </section>
  );
}

function ColourTokens(): React.JSX.Element {
  return (
    <div className="flex max-w-5xl flex-col gap-10">
      {COLOUR_GROUPS.map((group) => (
        <Section key={group.title} title={group.title} description={group.description}>
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {group.tokens.map((token) => (
              <li key={token.name} className="flex min-w-0 flex-col gap-1.5">
                <span
                  aria-hidden="true"
                  className={cn("h-14 rounded-lg border border-border shadow-xs", token.className)}
                />
                <code className="truncate font-mono text-xs text-foreground">--{token.name}</code>
                <code className="truncate font-mono text-2xs text-muted-foreground">
                  {token.className}
                </code>
              </li>
            ))}
          </ul>
        </Section>
      ))}
    </div>
  );
}

function TypeTokens(): React.JSX.Element {
  return (
    <div className="flex max-w-5xl flex-col gap-10">
      <Section
        title="Type scale"
        description="Dense and dashboard-first: body is 14px, tables and controls 13px. Inputs grow to 16px on touch screens so iOS never zooms."
      >
        <ul className="flex flex-col divide-y divide-border">
          {TYPE_SCALE.map((step) => (
            <li
              key={step.className}
              className="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:gap-6"
            >
              <code className="w-24 shrink-0 font-mono text-xs text-muted-foreground">
                {step.className}
              </code>
              <span className={cn("min-w-0 flex-1 truncate text-foreground", step.className)}>
                ₹4,50,000 drip system for 4.5 acres
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {step.size}px · {step.use}
              </span>
            </li>
          ))}
        </ul>
      </Section>
      <Section
        title="Weights"
        description="Three weights. Hierarchy comes from size and colour first."
      >
        <div className="flex flex-wrap gap-6 text-lg text-foreground">
          <span className="font-normal">Normal 400</span>
          <span className="font-medium">Medium 500</span>
          <span className="font-semibold">Semibold 600</span>
        </div>
      </Section>
      <Section
        title="Numbers and references"
        description="Tabular figures keep columns aligned. Mono is for IDs and error references. Check that ₹ renders in both."
      >
        <div className="flex flex-col gap-2 text-foreground">
          <span className="text-2xl font-semibold tabular-nums">
            ₹4.5 Cr · ₹1,25,000 · 1,11,111
          </span>
          <code className="font-mono text-sm text-muted-foreground">
            ₹ LEAD-001 · 3f2a9c1e-7b1d-4c55-9a0e-2d7c1f0b8e61
          </code>
        </div>
      </Section>
    </div>
  );
}

function RadiusTokens(): React.JSX.Element {
  return (
    <Section
      title="Radius"
      description="One knob: --radius. Every step is a multiple of it, so changing it reshapes the whole product."
    >
      <ul className="flex flex-wrap gap-6">
        {RADII.map((radius) => (
          <li key={radius.className} className="flex w-28 flex-col gap-2">
            <span
              aria-hidden="true"
              className={cn("size-20 border border-border-strong bg-muted", radius.className)}
            />
            <code className="font-mono text-xs text-foreground">{radius.className}</code>
            <span className="text-xs text-muted-foreground">{radius.use}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function ElevationTokens(): React.JSX.Element {
  return (
    <Section
      title="Elevation"
      description="Borders do most of the work; shadows are faint and only say how far a surface floats."
    >
      <ul className="flex flex-wrap gap-8 rounded-xl bg-background p-6">
        {SHADOWS.map((shadow) => (
          <li key={shadow.className} className="flex w-36 flex-col gap-2">
            <span
              aria-hidden="true"
              className={cn("h-20 rounded-xl border border-border bg-card", shadow.className)}
            />
            <code className="font-mono text-xs text-foreground">{shadow.className}</code>
            <span className="text-xs text-muted-foreground">{shadow.use}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function MotionSample({ label, classes }: { label: string; classes: string }): React.JSX.Element {
  const [moved, setMoved] = useState(false);

  return (
    <button
      type="button"
      aria-pressed={moved}
      onClick={() => {
        setMoved((current) => !current);
      }}
      className="flex h-control-md w-60 shrink-0 items-center rounded-md border border-border bg-muted px-1.5"
    >
      <span className="sr-only">Play {label}</span>
      <span
        aria-hidden="true"
        className={cn(
          "size-5 rounded-full bg-primary shadow-xs transition-transform",
          classes,
          moved ? "translate-x-48" : "translate-x-0",
        )}
      />
    </button>
  );
}

function MotionTokens(): React.JSX.Element {
  return (
    <div className="flex max-w-3xl flex-col gap-10">
      <Section
        title="Durations"
        description="UI motion stays under 300ms, and nothing opened a hundred times a day animates at all. Press a track to play it."
      >
        <ul className="flex flex-col gap-3">
          {DURATIONS.map((step) => (
            <li
              key={step.className}
              className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-6"
            >
              <MotionSample label={step.className} classes={cn(step.className, "ease-out")} />
              <span className="flex flex-col">
                <code className="font-mono text-xs text-foreground">
                  {step.className} · {step.ms}ms
                </code>
                <span className="text-xs text-muted-foreground">{step.use}</span>
              </span>
            </li>
          ))}
        </ul>
      </Section>
      <Section
        title="Easing"
        description="Custom curves — the built-in CSS ones are too weak. Never ease-in for interface motion."
      >
        <ul className="flex flex-col gap-3">
          {EASINGS.map((easing) => (
            <li
              key={easing.className}
              className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-6"
            >
              <MotionSample
                label={easing.className}
                classes={cn("duration-slow", easing.className)}
              />
              <span className="flex flex-col">
                <code className="font-mono text-xs text-foreground">{easing.className}</code>
                <span className="text-xs text-muted-foreground">{easing.use}</span>
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

const meta = {
  title: "Foundations/Tokens",
  parameters: { layout: "padded" },
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

export const Colours: Story = { render: () => <ColourTokens /> };

export const Typography: Story = { render: () => <TypeTokens /> };

export const Radius: Story = { render: () => <RadiusTokens /> };

export const Elevation: Story = { render: () => <ElevationTokens /> };

export const Motion: Story = { render: () => <MotionTokens /> };
