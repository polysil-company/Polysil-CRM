"use client";

import "leaflet/dist/leaflet.css";

import type { CircleMarker, LayerGroup, Map as LeafletMap } from "leaflet";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A map on OpenStreetMap tiles, drawn with Leaflet (BSD-2, no API key). The tiles are
 * OpenStreetMap's own, under their attribution.
 * TODO(TRK-001): heavy production use needs a tile provider or our own tile server, per the
 * OpenStreetMap tile usage policy; only `TILE_URL` changes.
 */
const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/** Gujarat, where most of the field team works: the view before there is anything to show. */
const DEFAULT_CENTRE: readonly [number, number] = [22.3, 71.2];
const DEFAULT_ZOOM = 7;

/** Token classes for a marker or a path; Leaflet puts them on the SVG element. */
const TONE_CLASSES = {
  primary: "fill-primary stroke-primary",
  success: "fill-success stroke-success",
  warning: "fill-warning stroke-warning",
  danger: "fill-danger stroke-danger",
  info: "fill-info stroke-info",
  muted: "fill-muted-foreground stroke-muted-foreground",
} as const;

export type MapTone = keyof typeof TONE_CLASSES;

export interface MapMarker {
  readonly id: string;
  readonly lat: number;
  readonly lng: number;
  /** Shown on hover and read by screen readers through the list beside the map. */
  readonly label: string;
  readonly tone: MapTone;
  /** Bigger for what matters most on the map (a person, a visit), smaller for a stop. */
  readonly size?: "sm" | "md" | "lg";
  /** A ring instead of a filled dot: something to treat with caution (a faked location). */
  readonly hollow?: boolean;
  readonly onSelect?: () => void;
}

export interface MapPath {
  readonly id: string;
  readonly points: readonly (readonly [number, number])[];
  readonly tone: MapTone;
}

const RADIUS = { sm: 5, md: 8, lg: 11 } as const;

/**
 * The map itself is an aid: every marker on it is also listed in words beside it, so nothing
 * depends on seeing or clicking the map. It fits itself to what it shows.
 */
export function MapView({
  markers,
  paths = [],
  label,
  className,
}: {
  markers: readonly MapMarker[];
  paths?: readonly MapPath[];
  /** The map's accessible name, e.g. "Team map". */
  label: string;
  className?: string;
}): React.JSX.Element {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const layer = useRef<LayerGroup | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const element = container.current;
    if (element === null) return undefined;
    import("leaflet")
      .then((leaflet) => {
        if (cancelled) return;
        const created = leaflet
          .map(element, { scrollWheelZoom: false })
          .setView([DEFAULT_CENTRE[0], DEFAULT_CENTRE[1]], DEFAULT_ZOOM);
        leaflet.tileLayer(TILE_URL, { attribution: ATTRIBUTION, maxZoom: 19 }).addTo(created);
        layer.current = leaflet.layerGroup().addTo(created);
        map.current = created;
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      layer.current = null;
    };
  }, []);

  useEffect(() => {
    const current = map.current;
    const group = layer.current;
    if (!ready || current === null || group === null) return;
    let cancelled = false;
    void import("leaflet").then((leaflet) => {
      if (cancelled) return;
      group.clearLayers();
      const bounds: [number, number][] = [];
      for (const path of paths) {
        if (path.points.length < 2) continue;
        const latLngs = path.points.map(([lat, lng]): [number, number] => [lat, lng]);
        leaflet
          .polyline(latLngs, { weight: 3, opacity: 0.85, className: TONE_CLASSES[path.tone] })
          .addTo(group);
        bounds.push(...latLngs);
      }
      for (const marker of markers) {
        const dot: CircleMarker = leaflet.circleMarker([marker.lat, marker.lng], {
          radius: RADIUS[marker.size ?? "md"],
          weight: 2,
          fillOpacity: marker.hollow === true ? 0 : 0.9,
          className: cn(TONE_CLASSES[marker.tone], "stroke-2"),
        });
        dot.bindTooltip(marker.label, { direction: "top" });
        const select = marker.onSelect;
        if (select !== undefined) dot.on("click", select);
        dot.addTo(group);
        bounds.push([marker.lat, marker.lng]);
      }
      if (bounds.length === 1) {
        const only = bounds[0];
        if (only !== undefined) current.setView(only, 13);
      } else if (bounds.length > 1) {
        current.fitBounds(bounds, { padding: [32, 32], maxZoom: 15 });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [ready, markers, paths]);

  return (
    <div className={cn("relative overflow-hidden rounded-xl border border-border", className)}>
      <div
        ref={container}
        role="region"
        aria-label={label}
        className="size-full dark:[&_.leaflet-tile-pane]:brightness-75 dark:[&_.leaflet-tile-pane]:contrast-125 dark:[&_.leaflet-tile-pane]:hue-rotate-180 dark:[&_.leaflet-tile-pane]:invert"
      />
      {failed ? (
        <p className="absolute inset-0 flex items-center justify-center bg-muted p-4 text-center text-sm text-muted-foreground">
          The map couldn&apos;t load. Everything on it is listed beside it.
        </p>
      ) : null}
    </div>
  );
}
