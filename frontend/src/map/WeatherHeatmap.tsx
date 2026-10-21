import L from 'leaflet'
import { useEffect, useRef, useState } from 'react'
import type { Heatmap } from '@/api/types'
import { ForecastSlider } from '@/map/ForecastSlider'
import { HeatmapLayer } from '@/map/HeatmapLayer'

/**
 * Heatmap plus its time slider. The hour lives here, so moving the slider
 * re-renders only this component, not the routes or checkpoints.
 */
export function WeatherHeatmap({ heatmap }: { heatmap: Heatmap }) {
  const [hour, setHour] = useState(0)
  const [shownHeatmap, setShownHeatmap] = useState(heatmap)
  const panelRef = useRef<HTMLDivElement>(null)

  // A new search starts the slider again at departure.
  if (heatmap !== shownHeatmap) {
    setShownHeatmap(heatmap)
    setHour(0)
  }

  // The panel sits inside the map: keep drags and wheel events from moving the map.
  useEffect(() => {
    if (!panelRef.current) return
    L.DomEvent.disableClickPropagation(panelRef.current)
    L.DomEvent.disableScrollPropagation(panelRef.current)
  }, [])

  return (
    <>
      <HeatmapLayer heatmap={heatmap} hour={hour} />
      <div ref={panelRef} className="absolute right-3 bottom-6 z-[1000] w-[min(26rem,calc(100%-1.5rem))]">
        <ForecastSlider
          startTime={heatmap.start_time}
          maxHour={heatmap.frame_count - 1}
          hour={hour}
          onChange={setHour}
        />
      </div>
    </>
  )
}
