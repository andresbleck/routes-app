import L from 'leaflet'
import 'leaflet.heat'
import { useEffect, useMemo, useRef } from 'react'
import { useMap } from 'react-leaflet'
import type { Heatmap } from '@/api/types'
import { RISK_COLORS } from '@/lib/risk'

// Intensity is severity / 4, so each risk level starts at a quarter step.
const GRADIENT = {
  0.1: RISK_COLORS.low,
  0.25: RISK_COLORS.moderate,
  0.5: RISK_COLORS.high,
  0.75: RISK_COLORS.severe,
  1: RISK_COLORS.no_travel,
}
const MIN_RADIUS_PX = 12

// leaflet.heat bug: removing the layer doesn't cancel a redraw already
// scheduled for the next frame, which then crashes on the missing map.
const heatPrototype = (L as unknown as { HeatLayer: { prototype: { _redraw(this: { _map: L.Map | null }): void } } })
  .HeatLayer.prototype
const redraw = heatPrototype._redraw
heatPrototype._redraw = function () {
  if (this._map) redraw.call(this)
}

interface HeatmapLayerProps {
  heatmap: Heatmap
  hour: number
}

/**
 * Weather severity heatmap. All 49 hourly frames are built up front; moving
 * the slider only swaps the points of one existing layer (no requests, no
 * React re-render of the map).
 */
export function HeatmapLayer({ heatmap, hour }: HeatmapLayerProps) {
  const map = useMap()
  const layerRef = useRef<L.HeatLayer | null>(null)

  const frames = useMemo(
    () =>
      heatmap.frames.map((values) =>
        heatmap.points.map(([lat, lon], i): L.HeatLatLngTuple => [lat, lon, values[i]]),
      ),
    [heatmap],
  )

  // One layer per heatmap; its radius follows the grid spacing at the current zoom.
  useEffect(() => {
    const layer = withReadbackHint(() =>
      L.heatLayer([], {
        ...radiusOptions(map, heatmap.grid_step_degrees),
        max: 1,
        maxZoom: 0, // leaflet.heat dims points below maxZoom; 0 keeps intensity constant
        minOpacity: 0,
        gradient: GRADIENT,
      }).addTo(map),
    )
    layerRef.current = layer

    const fitRadius = () => layer.setOptions(radiusOptions(map, heatmap.grid_step_degrees))
    map.on('zoomend', fitRadius)
    return () => {
      map.off('zoomend', fitRadius)
      layer.remove()
      layerRef.current = null
    }
  }, [map, heatmap])

  useEffect(() => {
    layerRef.current?.setLatLngs(frames[hour] ?? [])
  }, [frames, hour])

  return null
}

/**
 * leaflet.heat reads its whole canvas back (getImageData) on every redraw to
 * colorize it. On a GPU-backed canvas that readback was measured at 100–300 ms
 * per slider step; `willReadFrequently` keeps the canvas on the CPU. The
 * library creates its contexts itself, so the hint is applied only while the
 * layer is being created.
 */
function withReadbackHint<T>(create: () => T): T {
  const getContext = HTMLCanvasElement.prototype.getContext
  HTMLCanvasElement.prototype.getContext = function (
    this: HTMLCanvasElement,
    type: string,
    options?: CanvasRenderingContext2DSettings,
  ) {
    return getContext.call(this, type, type === '2d' ? { ...options, willReadFrequently: true } : options)
  } as typeof getContext
  try {
    return create()
  } finally {
    HTMLCanvasElement.prototype.getContext = getContext
  }
}

/** Radius and blur so neighbouring grid points just overlap into a continuous surface. */
function radiusOptions(map: L.Map, stepDegrees: number) {
  const center = map.getCenter()
  const a = map.latLngToContainerPoint(center)
  const b = map.latLngToContainerPoint([center.lat + stepDegrees, center.lng])
  const stepPx = Math.max(MIN_RADIUS_PX, a.distanceTo(b))
  return { radius: stepPx * 0.6, blur: stepPx * 0.6 }
}
