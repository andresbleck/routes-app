import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect } from 'react'
import { CircleMarker, MapContainer, Pane, TileLayer, Tooltip, useMap, ZoomControl } from 'react-leaflet'
import type { Route, TripPlan, TripPlanRequest } from '@/api/types'
import { CheckpointMarkers } from '@/map/CheckpointMarkers'
import { RiskLegend } from '@/map/RiskLegend'
import { RouteLayers } from '@/map/RouteLayers'
import { WeatherHeatmap } from '@/map/WeatherHeatmap'

const CONTINENTAL_US_CENTER: [number, number] = [39.5, -98.35]
const ESRI_CANVAS_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas'
const BASE_TILES_URL = `${ESRI_CANVAS_URL}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`
const LABEL_TILES_URL = `${ESRI_CANVAS_URL}/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`
const ESRI_ATTRIBUTION = 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ'
// Esri Canvas tiles exist up to z16; Leaflet upscales beyond that.
const MAX_NATIVE_ZOOM = 16
const ENDPOINT_COLOR = '#0f172a'

interface TripMapProps {
  plan: TripPlan | null
  trip: TripPlanRequest | null
  selectedRouteId: string | null
  onSelectRoute: (routeId: string) => void
}

export function TripMap({ plan, trip, selectedRouteId, onSelectRoute }: TripMapProps) {
  const selected = plan?.routes.find((route) => route.id === selectedRouteId) ?? null

  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={CONTINENTAL_US_CENTER}
        zoom={4}
        maxZoom={18}
        zoomControl={false}
        className="h-full w-full"
      >
        <TileLayer url={BASE_TILES_URL} attribution={ESRI_ATTRIBUTION} maxNativeZoom={MAX_NATIVE_ZOOM} />
        {/* Labels sit above routes and the heatmap so place names stay readable. */}
        <Pane name="labels" style={{ zIndex: 650, pointerEvents: 'none' }}>
          <TileLayer url={LABEL_TILES_URL} maxNativeZoom={MAX_NATIVE_ZOOM} />
        </Pane>
        <ZoomControl position="topright" />
        <FollowContainerSize />

        {plan && <WeatherHeatmap heatmap={plan.heatmap} />}

        {plan && selected && trip && (
          <>
            {/* Separate panes fix the drawing order: heatmap, routes, then markers on top. */}
            <Pane name="routes" style={{ zIndex: 410 }}>
              <RouteLayers routes={plan.routes} selectedId={selected.id} onSelect={onSelectRoute} />
            </Pane>
            <Pane name="markers" style={{ zIndex: 420 }}>
              <CheckpointMarkers checkpoints={selected.checkpoints} />
              <EndpointMarker position={[trip.origin.lat, trip.origin.lon]} label={`Origin · ${trip.origin.label}`} />
              <EndpointMarker
                position={[trip.destination.lat, trip.destination.lon]}
                label={`Destination · ${trip.destination.label}`}
              />
            </Pane>
            <FitToRoute route={selected} />
          </>
        )}
      </MapContainer>

      {plan && (
        // Hidden on phones to keep the small map readable; cards and the slider also show the colors.
        <div className="pointer-events-none absolute top-3 left-3 z-[1000] hidden max-w-[calc(100%-4.5rem)] sm:block">
          <RiskLegend />
        </div>
      )}
    </div>
  )
}

function EndpointMarker({ position, label }: { position: [number, number]; label: string }) {
  return (
    <CircleMarker
      center={position}
      radius={8}
      pathOptions={{ color: '#ffffff', weight: 3, fillColor: ENDPOINT_COLOR, fillOpacity: 1 }}
    >
      <Tooltip pane="tooltipPane" direction="top" offset={[0, -8]}>
        {label}
      </Tooltip>
    </CircleMarker>
  )
}

/**
 * Leaflet only listens to window resizes. On phones the map's height changes
 * with the sidebar content, so tell Leaflet whenever its container resizes.
 */
function FollowContainerSize() {
  const map = useMap()
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}

/** Frames the selected route whenever it changes. Not animated: an animated
 * zoom across several levels can leave stale tiles in the transparent labels layer. */
function FitToRoute({ route }: { route: Route }) {
  const map = useMap()
  useEffect(() => {
    // Extra room so the legend (top) and the forecast slider (bottom) don't cover the route.
    map.fitBounds(L.latLngBounds(route.geometry), {
      paddingTopLeft: [40, 64],
      paddingBottomRight: [40, 130],
      animate: false,
    })
  }, [map, route])
  return null
}
