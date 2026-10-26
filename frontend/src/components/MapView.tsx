import L from 'leaflet'
import { useEffect, useMemo, useRef, useState } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Circle, CircleMarker, GeoJSON, MapContainer, Marker, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { tileUrl } from '../api'
import { kmToMi } from '../format'
import { kindColor, theme } from '../theme'
import type { Geometry } from 'geojson'
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

// Where the map flies: a point and zoom, the search circle, or one water body's outline.
export type MapTarget = { center: [number, number]; zoom: number } | { circle: SearchCircle } | { geometry: Geometry }

interface Props {
  target: MapTarget
  spots: MapSpot[]
  selectedId: string | null
  gibsDate: string | null
  chlTime: string | null
  lens: number
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
      <span class="ring" style="background:${color}55;box-shadow:0 0 22px ${color}"></span>
      <span class="core" style="background:${color};color:${color}"><span style="color:#06142b;display:grid;place-items:center">${inner}</span></span>
    </div>`,
  })
}

function FlyTo({ target }: { target: MapTarget }) {
  const map = useMap()
  useEffect(() => {
    if ('circle' in target) {
      const { lat, lon, km } = target.circle
      map.flyToBounds(L.latLng(lat, lon).toBounds(km * 2000), { padding: [24, 24], duration: 1.1 })
    } else if ('geometry' in target) {
      map.flyToBounds(L.geoJSON(target.geometry).getBounds(), { padding: [48, 48], maxZoom: 15, duration: 1.1 })
    } else {
      map.flyTo(target.center, target.zoom, { duration: 1.1 })
    }
  }, [map, target])
  return null
}

function ClickCatcher({ onMapClick, onZoom }: { onMapClick?: (lat: number, lon: number) => void; onZoom: (z: number) => void }) {
  const map = useMapEvents({
    click(e) {
      onMapClick?.(e.latlng.lat, e.latlng.lng)
    },
    zoomend() {
      onZoom(map.getZoom())
    },
  })
  return null
}

function ImageryLegend({ zoom, gibsDate }: { zoom: number; gibsDate: string | null }) {
  const daily = zoom <= GIBS_NATIVE_MAX
  return (
    <div className="glass-strong pointer-events-none absolute top-3 left-3 z-[600] max-w-[300px] rounded-xl px-3 py-2 text-[11px] leading-snug text-slate-200">
      <p className="font-semibold text-teal-100">
        Imagery at zoom {zoom}: {daily ? 'daily satellite pass' : 'detail orthoimagery'}
      </p>
      {daily ? (
        <p className="text-slate-300">
          NOAA-20 VIIRS true color{gibsDate ? `, ${gibsDate}` : ' (unavailable)'} · NASA GIBS · about 250 m per pixel. Zoom in past{' '}
          {GIBS_NATIVE_MAX} for detail.
        </p>
      ) : (
        <p className="text-slate-300">
          USDA/USGS aerial orthoimagery (The National Map, refreshed June 2024), not today's. Zoom out to {GIBS_NATIVE_MAX} or
          less for the daily NOAA-20 pass. Max zoom {ORTHO_NATIVE_MAX}.
        </p>
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

function shapeStyle(kind: string, highlighted: boolean): L.PathOptions {
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

function WaterShape({ body, highlighted, onClick, onHover }: { body: WaterBody; highlighted: boolean; onClick: () => void; onHover: (on: boolean) => void }) {
  const style = useMemo(() => shapeStyle(body.kind, highlighted), [body.kind, highlighted])
  return (
    <GeoJSON
      data={body.geometry}
      style={style}
      pointToLayer={(_, latlng) => L.circleMarker(latlng, { radius: 7 })}
      eventHandlers={{ click: onClick, mouseover: () => onHover(true), mouseout: () => onHover(false) }}
    >
      <Tooltip sticky>
        <div className="text-xs">
          <strong>{body.name}</strong>
          <div>
            {body.kind} · {kmToMi(body.distance_km)} mi away
          </div>
          {body.halo && <div>{body.halo.label}</div>}
        </div>
      </Tooltip>
    </GeoJSON>
  )
}

export default function MapView(props: Props) {
  const { target, spots, selectedId, gibsDate, chlTime, lens, scanning, offline, circle, origin, water, highlightId } = props
  const { onSpotClick, onWaterClick, onWaterHover, onMapClick } = props
  const baseUrl = tileUrl('base')
  const orthoUrl = tileUrl('ortho')
  const gibsUrl = gibsDate ? tileUrl('gibs', `?date=${gibsDate}`) : null
  const chlUrl = chlTime ? tileUrl('chl', `?date=${encodeURIComponent(chlTime)}`) : null
  const [start] = useState(() => ('center' in target ? target : { center: [32.8, -117.25] as [number, number], zoom: 11 }))
  const [viewZoom, setViewZoom] = useState(start.zoom)
  const imageryOpacity = 1 - lens * 0.55
  const icons = useMemo(
    () => new Map(spots.map((s) => [s.id, haloIcon(s.halo, s.id === selectedId)])),
    [spots, selectedId],
  )

  return (
    <div className="relative h-full w-full overflow-hidden rounded-2xl">
      <MapContainer center={start.center} zoom={start.zoom} minZoom={3} maxZoom={MAP_MAX_ZOOM} className="h-full w-full" zoomControl={false} worldCopyJump>
        <TileLayer
          key={`base-${offline}`}
          url={baseUrl}
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          maxZoom={MAP_MAX_ZOOM}
        />
        <TileLayer
          key={`ortho-${offline}`}
          url={orthoUrl}
          minZoom={ORTHO_MIN}
          maxNativeZoom={ORTHO_NATIVE_MAX}
          maxZoom={ORTHO_NATIVE_MAX}
          opacity={imageryOpacity}
          attribution='Orthoimagery: <a href="https://www.usgs.gov/programs/national-geospatial-program/national-map">USDA, USGS The National Map</a>'
        />
        {gibsUrl && (
          <TileLayer
            key={`gibs-${gibsDate}-${offline}`}
            url={gibsUrl}
            maxNativeZoom={GIBS_NATIVE_MAX}
            maxZoom={GIBS_NATIVE_MAX}
            opacity={imageryOpacity}
            attribution='Daily imagery: <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a> (NOAA-20 VIIRS)'
          />
        )}
        {chlUrl && lens > 0.02 && (
          <TileLayer
            key={`chl-${chlTime}-${offline}`}
            url={chlUrl}
            maxZoom={MAP_MAX_ZOOM}
            opacity={lens}
            attribution='Chlorophyll: <a href="https://coastwatch.noaa.gov/erddap/">NOAA CoastWatch ERDDAP</a>'
          />
        )}
        <FlyTo target={target} />
        <ClickCatcher onMapClick={onMapClick} onZoom={setViewZoom} />
        {circle && <RadiusRing lat={circle.lat} lon={circle.lon} km={circle.km} />}
        {water.map((b) => (
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
      <ImageryLegend zoom={viewZoom} gibsDate={gibsDate} />
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
