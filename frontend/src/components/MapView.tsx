import L from 'leaflet'
import { useEffect, useMemo, useRef, useState } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Circle, CircleMarker, GeoJSON, MapContainer, Marker, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { tileUrl } from '../api'
import { kmToMi } from '../format'
import { Info } from 'lucide-react'
import { kindColor, theme } from '../theme'
import type { Halo, WaterBody } from '../types'
import { HaloIcon } from './common'

export interface MapSpot {
  id: string
  name: string
  lat: number
  lon: number
  halo: Halo | null
  subtitle?: string
}

export interface SearchCircle {
  lat: number
  lon: number
  km: number
}

// Where the map flies: a point and zoom, or the bounds of the search circle.
export type MapTarget = { center: [number, number]; zoom: number } | { circle: SearchCircle }

interface Props {
  target: MapTarget
  spots: MapSpot[]
  selectedId: string | null
  gibsDate: string | null
  scanning: boolean
  offline: boolean
  circle: SearchCircle | null
  origin: { lat: number; lon: number; name: string } | null
  water: WaterBody[]
  highlightId: string | null
  onSpotClick?: (spot: MapSpot) => void
  onWaterClick: (body: WaterBody) => void
  onWaterHover: (id: string | null) => void
  onMapClick?: (lat: number, lon: number) => void
}

// Native zoom limits (match backend/app/config.py). maxZoom never exceeds a layer's native zoom,
// so Leaflet never stretches tiles.
const GIBS_NATIVE_MAX = 9
const ORTHO_MIN = 10
const ORTHO_NATIVE_MAX = 16
const MAP_MAX_ZOOM = ORTHO_NATIVE_MAX

function haloIcon(halo: Halo | null, selected: boolean): L.DivIcon {
  const color = halo ? theme.halo[halo.color] : '#94a3b8'
  const inner = renderToStaticMarkup(<HaloIcon icon={halo?.icon ?? 'unknown'} size={12} />)
  return L.divIcon({
    className: '',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    html: `<div class="halo-marker${selected ? ' selected' : ''}" role="img" aria-label="${halo?.label ?? 'Status unknown'}">
      <span class="ring" style="background:${color}55"></span>
      <span class="core" style="background:${color};color:${color}"><span style="color:#06142b;display:grid;place-items:center">${inner}</span></span>
    </div>`,
  })
}

function FlyTo({ target }: { target: MapTarget }) {
  const map = useMap()
  useEffect(() => {
    if ('circle' in target) {
      const { lat, lon, km } = target.circle
      // On a phone the bottom sheet covers the lower 40% of the map, so keep the circle above it.
      const sheet = window.innerWidth < 1024 ? Math.round(map.getSize().y * 0.4) : 0
      map.flyToBounds(L.latLng(lat, lon).toBounds(km * 2000), { paddingTopLeft: [24, 24], paddingBottomRight: [24, 24 + sheet], duration: 1.1 })
    } else {
      map.flyTo(target.center, target.zoom, { duration: 1.1 })
    }
  }, [map, target])
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

const CREDITS: { label: string; href: string }[] = [
  { label: 'Base: NASA Blue Marble (GIBS)', href: 'https://earthdata.nasa.gov/gibs' },
  { label: 'Aerial photo: USDA, USGS The National Map', href: 'https://www.usgs.gov/programs/national-geospatial-program/national-map' },
  { label: 'Daily pass: NASA GIBS, NOAA-20 VIIRS', href: 'https://earthdata.nasa.gov/gibs' },
  { label: 'Places: OpenStreetMap contributors (ODbL)', href: 'https://www.openstreetmap.org/copyright' },
  { label: 'Map library: Leaflet', href: 'https://leafletjs.com' },
]

function Credits() {
  const [open, setOpen] = useState(false)
  return (
    <div className="absolute top-3 right-3 z-[650] flex flex-col items-end gap-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="map-credits"
        aria-label="Map credits"
        className="glass-strong grid h-9 w-9 place-items-center rounded-full text-slate-100 hover:bg-white/10"
      >
        <Info size={16} aria-hidden />
      </button>
      {open && (
        <ul id="map-credits" className="glass-strong w-64 space-y-1 rounded-xl p-3 text-xs leading-5">
          {CREDITS.map((c) => (
            <li key={c.label}>
              <a href={c.href} target="_blank" rel="noreferrer" className="text-teal-200 underline-offset-2 hover:underline">
                {c.label}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
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

function RadiusRing({ lat, lon, km }: SearchCircle) {
  const radius = useAnimatedNumber(km * 1000)
  return (
    <Circle
      center={[lat, lon]}
      radius={radius}
      interactive={false}
      pathOptions={{ color: theme.teal, weight: 2, opacity: 0.85, fillColor: theme.teal, fillOpacity: 0.05, dashArray: '6 8' }}
    />
  )
}

function shapeStyle(kind: string, highlighted: boolean, hasData: boolean): L.PathOptions {
  if (!hasData) {
    // No data: gray and dashed, so it reads as not clickable
    const line = { color: theme.noData, weight: kind === 'river' ? 3 : 1.5, opacity: 0.8, dashArray: '4 4' }
    return kind === 'river' ? line : { ...line, fillColor: theme.noData, fillOpacity: 0.25 }
  }
  const color = kindColor(kind)
  if (kind === 'river') {
    return { color: highlighted ? '#ffffff' : color, weight: highlighted ? 6 : 4, opacity: 0.95 }
  }
  return {
    color: highlighted ? '#ffffff' : kind === 'beach' ? color : theme.waterLine,
    weight: highlighted ? 3 : 1.5,
    opacity: 1,
    fillColor: color,
    fillOpacity: highlighted ? 0.7 : 0.45,
  }
}

// Adds the no-data class (not-allowed cursor) to every path. A river with several segments is a nested group.
function markNoData(layer: L.Layer) {
  if (layer instanceof L.LayerGroup) layer.eachLayer(markNoData)
  else if (layer instanceof L.Path) layer.getElement()?.classList.add('no-data')
}

function WaterShape({ body, highlighted, onClick, onHover }: { body: WaterBody; highlighted: boolean; onClick: () => void; onHover: (on: boolean) => void }) {
  const hasData = body.report_available
  const style = useMemo(() => shapeStyle(body.kind, highlighted, hasData), [body.kind, highlighted, hasData])
  return (
    <GeoJSON
      data={body.geometry}
      style={style}
      pointToLayer={(_, latlng) => L.circleMarker(latlng, { radius: 7 })}
      eventHandlers={
        hasData
          ? { click: onClick, mouseover: () => onHover(true), mouseout: () => onHover(false) }
          : { add: (e) => markNoData(e.target as L.Layer) }
      }
    >
      <Tooltip sticky>
        <div className="text-xs">
          <strong>{body.name}</strong>
          <div>
            {body.kind} · {kmToMi(body.distance_km)} mi away
          </div>
          {hasData ? (
            <>
              {body.halo && <div>{body.halo.label}</div>}
              <div className="font-semibold">Click to open the report</div>
            </>
          ) : (
            <div className="font-semibold">No data. Cannot open a report.</div>
          )}
        </div>
      </Tooltip>
    </GeoJSON>
  )
}

export default function MapView(props: Props) {
  const { target, spots, selectedId, gibsDate, scanning, offline, circle, origin, water, highlightId } = props
  const { onSpotClick, onWaterClick, onWaterHover, onMapClick } = props
  const baseUrl = tileUrl('base')
  const orthoUrl = tileUrl('ortho')
  const gibsUrl = gibsDate ? tileUrl('gibs', `?date=${gibsDate}`) : null
  const [start] = useState(() => ('center' in target ? target : { center: [32.8, -117.25] as [number, number], zoom: 11 }))
  const icons = useMemo(
    () => new Map(spots.map((s) => [s.id, haloIcon(s.halo, s.id === selectedId)])),
    [spots, selectedId],
  )

  return (
    <div className="relative h-full w-full overflow-hidden lg:rounded-2xl">
      <MapContainer center={start.center} zoom={start.zoom} minZoom={3} maxZoom={MAP_MAX_ZOOM} className="h-full w-full" zoomControl={false} attributionControl={false} worldCopyJump>
        <TileLayer
          key={`base-${offline}`}
          url={baseUrl}
          maxZoom={MAP_MAX_ZOOM}
        />
        <TileLayer
          key={`ortho-${offline}`}
          url={orthoUrl}
          minZoom={ORTHO_MIN}
          maxNativeZoom={ORTHO_NATIVE_MAX}
          maxZoom={ORTHO_NATIVE_MAX}
        />
        {gibsUrl && (
          <TileLayer
            key={`gibs-${gibsDate}-${offline}`}
            url={gibsUrl}
            maxNativeZoom={GIBS_NATIVE_MAX}
            maxZoom={GIBS_NATIVE_MAX}
            />
        )}
        <FlyTo target={target} />
        <ClickCatcher onMapClick={onMapClick} />
        {circle && <RadiusRing lat={circle.lat} lon={circle.lon} km={circle.km} />}
        {/* No-data shapes first, so shapes with data sit on top and get the clicks */}
        {[...water].sort((a, b) => Number(a.report_available) - Number(b.report_available)).map((b) => (
          <WaterShape
            key={b.id}
            body={b}
            highlighted={b.id === highlightId}
            onClick={() => onWaterClick(b)}
            onHover={(on) => onWaterHover(on ? b.id : null)}
          />
        ))}
        {origin && (
          <CircleMarker center={[origin.lat, origin.lon]} radius={7} pathOptions={{ color: '#fff', fillColor: theme.teal, fillOpacity: 1, weight: 2 }}>
            <Tooltip direction="top">Starting address: {origin.name}</Tooltip>
          </CircleMarker>
        )}
        {spots.map((s) => (
          <Marker
            key={s.id}
            position={[s.lat, s.lon]}
            icon={icons.get(s.id)!}
            eventHandlers={{ click: () => onSpotClick?.(s) }}
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
      <Credits />
      {scanning && (
        <div className="pointer-events-none absolute inset-0 z-[500]">
          <div className="scan-line" />
          <div className="glass-strong absolute top-3 left-1/2 hidden -translate-x-1/2 rounded-full lg:block px-3 py-1 text-xs font-semibold tracking-widest text-teal-100 uppercase">
            NOAA-20 pass
          </div>
        </div>
      )}
    </div>
  )
}
