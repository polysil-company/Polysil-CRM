import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { MapView, type MapMarker, type MapPath } from "./map-view";

const TEAM: readonly MapMarker[] = [
  {
    id: "a",
    lat: 22.3039,
    lng: 70.8022,
    label: "Aarav Desai, on duty",
    tone: "success",
    size: "lg",
  },
  {
    id: "b",
    lat: 21.5222,
    lng: 70.4579,
    label: "Ravi Patel, on duty",
    tone: "success",
    size: "lg",
  },
  {
    id: "c",
    lat: 21.6032,
    lng: 71.2221,
    label: "Kiran Solanki, not heard from",
    tone: "muted",
    size: "lg",
  },
  {
    id: "d",
    lat: 21.7645,
    lng: 72.1519,
    label: "Meena Chauhan, fake location",
    tone: "danger",
    size: "lg",
    hollow: true,
  },
];

const ROUTE: readonly MapPath[] = [
  {
    id: "route",
    tone: "primary",
    points: [
      [21.5222, 70.4579],
      [21.55, 70.5],
      [21.58, 70.56],
      [21.6, 70.62],
      [21.57, 70.66],
    ],
  },
];

const meta = {
  title: "Patterns/MapView",
  component: MapView,
  args: { markers: TEAM, label: "Team map", className: "h-96" },
} satisfies Meta<typeof MapView>;

export default meta;

type Story = StoryObj<typeof meta>;

/** People as dots coloured by state; a faked location is a red ring. */
export const Team: Story = {};

/** A day's path with its stops and visits. */
export const Route: Story = {
  args: {
    label: "Route of Ravi Patel",
    paths: ROUTE,
    markers: [
      { id: "start", lat: 21.5222, lng: 70.4579, label: "Start, 9:10 am", tone: "info" },
      {
        id: "visit",
        lat: 21.58,
        lng: 70.56,
        label: "Visit, 11:02 am",
        tone: "success",
        size: "lg",
      },
      { id: "stop", lat: 21.6, lng: 70.62, label: "Stop, 22 min", tone: "muted", size: "sm" },
      { id: "end", lat: 21.57, lng: 70.66, label: "Last point, 6:31 pm", tone: "danger" },
    ],
  },
};

/** Nothing to show yet: the map opens on Gujarat. */
export const Empty: Story = { args: { markers: [] } };
