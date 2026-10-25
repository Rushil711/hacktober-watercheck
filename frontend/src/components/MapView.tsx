import L from 'leaflet'
import { useEffect, useMemo, useRef, useState } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Circle, CircleMarker, MapContainer, Marker, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { tileUrl } from '../api'
import { theme } from '../theme'
import type { Halo } from '../types'
import { HaloIcon } from './common'

export interface MapSpot {
  id: string
  name: string
  lat: number
  lon: number
  halo: Halo | null
  subtitle?: string
}

interface Props {
  center: [number, number]
  zoom: number
  spots: MapSpot[]
  selectedId: string | null
  gibsDate: string | null
  chlTime: string | null
  lens: number
  scanning: boolean
  offline: boolean
  ring: { lat: number; lon: number; km: number } | null
  origin: { lat: number; lon: number } | null
  onSpotClick: (spot: MapSpot) => void
  onMapClick?: (lat: number, lon: number) => void
}

function haloIcon(halo: Halo | null, selected: boolean): L.DivIcon {
  const color = halo ? theme.halo[halo.color] : '#94a3b8'
  const inner = renderToStaticMarkup(<HaloIcon icon={halo?.icon ?? 'unknown'} size={12} />)
  return L.divIcon({
    className: '',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    html: `<div class="halo-marker${selected ? ' selected' : ''}" role="img" aria-label="${halo?.label ?? 'Status unknown'}">
      <span class="ring" style="background:${color}55;box-shadow:0 0 22px ${color}"></span>
      <span class="core" style="background:${color};color:${color}"><span style="color:#06142b;display:grid;place-items:center">${inner}</span></span>
    </div>`,
  })
}

function FlyTo({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap()
  useEffect(() => {
    map.flyTo(center, zoom, { duration: 1.1 })
  }, [map, center, zoom])
  return null
}

function ClickCatcher({ onMapClick }: { onMapClick?: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onMapClick?.(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

function useAnimatedNumber(target: number, ms = 600): number {
  const [value, setValue] = useState(target)
  const fromRef = useRef(target)
  useEffect(() => {
    const from = fromRef.current
    const start = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms)
      const eased = 1 - Math.pow(1 - t, 3)
      const v = from + (target - from) * eased
      setValue(v)
      fromRef.current = v
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, ms])
  return value
}

function DriveRing({ lat, lon, km }: { lat: number; lon: number; km: number }) {
  const radius = useAnimatedNumber(km * 1000)
  return (
    <Circle
      center={[lat, lon]}
      radius={radius}
      pathOptions={{ color: theme.teal, weight: 1.5, opacity: 0.7, fillColor: theme.teal, fillOpacity: 0.06, dashArray: '6 8' }}
    />
  )
}

export default function MapView(props: Props) {
  const { center, zoom, spots, selectedId, gibsDate, chlTime, lens, scanning, offline, ring, origin, onSpotClick, onMapClick } = props
  const baseUrl = tileUrl('base')
  const gibsUrl = gibsDate ? tileUrl('gibs', `?date=${gibsDate}`) : null
  const chlUrl = chlTime ? tileUrl('chl', `?date=${encodeURIComponent(chlTime)}`) : null
  const icons = useMemo(
    () => new Map(spots.map((s) => [s.id, haloIcon(s.halo, s.id === selectedId)])),
    [spots, selectedId],
  )

  return (
    <div className="relative h-full w-full overflow-hidden rounded-2xl">
      <MapContainer center={center} zoom={zoom} className="h-full w-full" zoomControl={false} worldCopyJump>
        <TileLayer
          key={`base-${offline}`}
          url={baseUrl}
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          maxZoom={18}
        />
        {gibsUrl && (
          <TileLayer
            key={`gibs-${gibsDate}-${offline}`}
            url={gibsUrl}
            maxNativeZoom={9}
            maxZoom={18}
            opacity={1 - lens * 0.55}
            attribution='Imagery: <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a> (NOAA-20 VIIRS)'
          />
        )}
        {chlUrl && lens > 0.02 && (
          <TileLayer
            key={`chl-${chlTime}-${offline}`}
            url={chlUrl}
            maxZoom={18}
            opacity={lens}
            attribution='Chlorophyll: <a href="https://coastwatch.noaa.gov/erddap/">NOAA CoastWatch ERDDAP</a>'
          />
        )}
        <FlyTo center={center} zoom={zoom} />
        <ClickCatcher onMapClick={onMapClick} />
        {ring && <DriveRing lat={ring.lat} lon={ring.lon} km={ring.km} />}
        {origin && (
          <CircleMarker center={[origin.lat, origin.lon]} radius={7} pathOptions={{ color: '#fff', fillColor: theme.teal, fillOpacity: 1, weight: 2 }}>
            <Tooltip direction="top">Search center</Tooltip>
          </CircleMarker>
        )}
        {spots.map((s) => (
          <Marker
            key={s.id}
            position={[s.lat, s.lon]}
            icon={icons.get(s.id)!}
            eventHandlers={{ click: () => onSpotClick(s) }}
            keyboard
            title={s.name}
          >
            <Tooltip direction="top" offset={[0, -14]}>
              <div className="text-xs">
                <strong>{s.name}</strong>
                {s.halo && <div>{s.halo.label}</div>}
                {s.subtitle && <div>{s.subtitle}</div>}
              </div>
            </Tooltip>
          </Marker>
        ))}
      </MapContainer>
      {scanning && (
        <div className="pointer-events-none absolute inset-0 z-[500]">
          <div className="scan-line" />
          <div className="glass-strong absolute top-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-1 text-[11px] font-semibold tracking-widest text-teal-100 uppercase">
            NOAA-20 pass
          </div>
        </div>
      )}
    </div>
  )
}
