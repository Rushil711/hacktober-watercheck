import { AnimatePresence, motion } from 'framer-motion'
import { Layers, MapPin, Navigation, Search, Sparkles, Waves, Wifi, WifiOff } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { api, setOffline as setApiOffline } from './api'
import { Empty, ErrorBox, Loading } from './components/common'
import MapView, { type MapSpot } from './components/MapView'
import NearbyPanel from './components/NearbyPanel'
import ReportPanel from './components/ReportPanel'
import { FEATURES } from './features'
import type { AppConfig, BeachReport, Candidate, Health, Insights, NearbyResult, SearchResult } from './types'

type Mode = 'spot' | 'near'
type SpotRef = { name: string; lat: number; lon: number; kind: string }

const DEFAULT_CENTER: [number, number] = [32.8, -117.25]

function yesterdayUtc(): string {
  const d = new Date(Date.now() - 86400000)
  return d.toISOString().slice(0, 10)
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : 'Unexpected error'
}

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [voice, setVoice] = useState<{ configured: boolean; problem: string | null; docs_url: string } | null>(null)
  const [bootError, setBootError] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('spot')
  const [offline, setOffline] = useState(false)

  const [query, setQuery] = useState('')
  const [search, setSearch] = useState<SearchResult | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  const [spot, setSpot] = useState<SpotRef | null>(null)
  const [report, setReport] = useState<BeachReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)
  const [insights, setInsights] = useState<Insights | null>(null)
  const [insightsLoading, setInsightsLoading] = useState(false)
  const [insightsError, setInsightsError] = useState<string | null>(null)

  const [center, setCenter] = useState<[number, number]>(DEFAULT_CENTER)
  const [zoom, setZoom] = useState(11)
  const [lens, setLens] = useState(0)

  const [origin, setOrigin] = useState<{ lat: number; lon: number } | null>(null)
  const [driveMin, setDriveMin] = useState(30)
  const [nearby, setNearby] = useState<NearbyResult | null>(null)
  const [nearbyLoading, setNearbyLoading] = useState(false)
  const [nearbyError, setNearbyError] = useState<string | null>(null)
  const [locating, setLocating] = useState(false)
  const [askLoading, setAskLoading] = useState(false)
  const [askNote, setAskNote] = useState<string | null>(null)
  const [minTempFilter, setMinTempFilter] = useState<number | null>(null)

  const presentationIndex = useRef(-1)
  const reportAbort = useRef<AbortController | null>(null)
  const nearbyAbort = useRef<AbortController | null>(null)

  const refreshStatus = useCallback(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
    api.voiceStatus().then(setVoice).catch(() => setVoice(null))
  }, [])

  const openSpot = useCallback(async (target: SpotRef) => {
    reportAbort.current?.abort()
    const ctrl = new AbortController()
    reportAbort.current = ctrl
    setMode('spot')
    setSpot(target)
    setSearch(null)
    setCenter([target.lat, target.lon])
    setZoom(11)
    setReport(null)
    setReportError(null)
    setInsights(null)
    setInsightsError(null)
    setReportLoading(true)
    try {
      const r = await api.report(target, ctrl.signal)
      setReport(r)
      setReportLoading(false)
      if (!FEATURES.gemma) return
      setInsightsLoading(true)
      try {
        setInsights(await api.insights(r, ctrl.signal))
      } catch (e) {
        if (!ctrl.signal.aborted) setInsightsError(errMsg(e))
      } finally {
        if (!ctrl.signal.aborted) setInsightsLoading(false)
      }
    } catch (e) {
      if (!ctrl.signal.aborted) {
        setReportError(errMsg(e))
        setReportLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    api
      .config()
      .then((c) => {
        setConfig(c)
        const p = new URLSearchParams(window.location.search)
        const lat = Number(p.get('lat'))
        const lon = Number(p.get('lon'))
        if (p.has('lat') && p.has('lon') && Number.isFinite(lat) && Number.isFinite(lon)) {
          openSpot({ name: p.get('name') ?? 'Selected spot', lat, lon, kind: p.get('kind') ?? 'beach' })
        }
      })
      .catch((e) => setBootError(`Backend not reachable: ${errMsg(e)}. Start it with uvicorn (see README).`))
    refreshStatus()
    const t = setInterval(refreshStatus, 15000)
    return () => clearInterval(t)
  }, [refreshStatus, openSpot])

  const runSearch = async (e: FormEvent) => {
    e.preventDefault()
    const q = query.trim()
    if (q.length < 2) return
    setMode('spot')
    setSearchLoading(true)
    setSearchError(null)
    setSearch(null)
    try {
      const res = await api.search(q)
      setSearch(res)
      if (res.place) {
        setCenter([res.place.lat, res.place.lon])
        setZoom(13)
      }
    } catch (err) {
      setSearchError(errMsg(err))
    } finally {
      setSearchLoading(false)
    }
  }

  const loadNearby = useCallback(async (o: { lat: number; lon: number }, minutes: number) => {
    nearbyAbort.current?.abort()
    const ctrl = new AbortController()
    nearbyAbort.current = ctrl
    setNearbyLoading(true)
    setNearbyError(null)
    try {
      const res = await api.nearby(o.lat, o.lon, minutes, ctrl.signal)
      setNearby(res)
    } catch (e) {
      if (!ctrl.signal.aborted) setNearbyError(errMsg(e))
    } finally {
      if (!ctrl.signal.aborted) setNearbyLoading(false)
    }
  }, [])

  const setPin = (lat: number, lon: number) => {
    const o = { lat, lon }
    setOrigin(o)
    setMinTempFilter(null)
    setAskNote(null)
    setCenter([lat, lon])
    setZoom(driveMin >= 60 ? 9 : 10)
    loadNearby(o, driveMin)
  }

  const changeDrive = (m: number) => {
    setDriveMin(m)
    if (origin) {
      setZoom(m >= 60 ? 9 : 10)
      loadNearby(origin, m)
    }
  }

  const locate = () => {
    if (!navigator.geolocation) {
      setNearbyError('This browser does not share location. Drop a pin instead.')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        setPin(pos.coords.latitude, pos.coords.longitude)
      },
      (err) => {
        setLocating(false)
        setNearbyError(`Location unavailable (${err.message}). Drop a pin instead.`)
      },
      { timeout: 10000 },
    )
  }

  const ask = async (question: string) => {
    setAskLoading(true)
    setAskNote(null)
    try {
      const res = await api.naturalSearch(question, origin)
      if (!res.filter.ok || !res.filter.data) {
        setAskNote(`Gemma could not turn that into a filter (${res.filter.error ?? 'invalid reply'}). Use the controls instead.`)
        return
      }
      const f = res.filter.data
      setDriveMin(f.max_drive_min)
      setMinTempFilter(f.min_temp_f)
      if (res.origin) {
        setOrigin({ lat: res.origin.lat, lon: res.origin.lon })
        setCenter([res.origin.lat, res.origin.lon])
        setZoom(f.max_drive_min >= 60 ? 9 : 10)
      }
      if (res.result) setNearby(res.result)
      setAskNote(
        `Gemma filter: within ${f.max_drive_min} min${f.near ? ` of ${f.near}` : ''}` +
          `${f.min_temp_f !== null ? `, sea temp ≥ ${f.min_temp_f} °F` : ''}, activity: ${f.activity}.` +
          (res.warnings.length ? ` ${res.warnings.join(' ')}` : ''),
      )
    } catch (e) {
      setAskNote(errMsg(e))
    } finally {
      setAskLoading(false)
    }
  }

  const spotRef = useRef<SpotRef | null>(null)
  useEffect(() => {
    spotRef.current = mode === 'spot' ? spot : null
  }, [mode, spot])

  useEffect(() => {
    if (!FEATURES.presentationKeys) return
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'p' || e.key === 'P') {
        if (!config?.demo_beaches.length) return
        presentationIndex.current = (presentationIndex.current + 1) % config.demo_beaches.length
        const b = config.demo_beaches[presentationIndex.current]
        openSpot({ name: b.name, lat: b.lat, lon: b.lon, kind: b.kind })
      } else if (e.key === 'o' || e.key === 'O') {
        setOffline((v) => {
          const next = !v
          setApiOffline(next)
          return next
        })
        if (spotRef.current) openSpot(spotRef.current)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [config, openSpot])

  const filteredNearby = useMemo(() => {
    if (!nearby || minTempFilter === null) return nearby
    return { ...nearby, spots: nearby.spots.filter((s) => s.sea_temp_f !== null && s.sea_temp_f >= minTempFilter) }
  }, [nearby, minTempFilter])

  const mapSpots: MapSpot[] = useMemo(() => {
    if (mode === 'near') {
      return (filteredNearby?.spots ?? []).map((s) => ({
        id: `${s.name}-${s.lat}-${s.lon}`,
        name: s.name,
        lat: s.lat,
        lon: s.lon,
        halo: s.halo,
        subtitle: `${Math.round(s.drive_min)} min drive`,
      }))
    }
    const list: MapSpot[] = []
    if (spot) list.push({ id: 'selected', name: spot.name, lat: spot.lat, lon: spot.lon, halo: report?.halo ?? null })
    for (const c of search?.candidates ?? []) list.push({ id: `c-${c.name}-${c.lat}`, name: c.name, lat: c.lat, lon: c.lon, halo: null, subtitle: 'Click to check' })
    return list
  }, [mode, filteredNearby, spot, report, search])

  const onSpotClick = (s: MapSpot) => {
    if (s.id === 'selected') return
    const kind = mode === 'near' ? filteredNearby?.spots.find((n) => `${n.name}-${n.lat}-${n.lon}` === s.id)?.kind ?? 'beach' : search?.candidates.find((c) => `c-${c.name}-${c.lat}` === s.id)?.kind ?? 'beach'
    openSpot({ name: s.name, lat: s.lat, lon: s.lon, kind })
  }

  const scanning = reportLoading || nearbyLoading || searchLoading
  const statusBadge = offline || health?.demo_mode

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-teal-400/20 text-teal-200">
            <Waves size={20} />
          </div>
          <div>
            <h1 className="text-lg leading-none font-bold text-white">WaterCheck</h1>
            <p className="text-[11px] text-slate-400">Satellite + official data · explained by Gemma</p>
          </div>
        </div>
        <form onSubmit={runSearch} className="flex min-w-[260px] flex-1 items-center gap-2">
          <div className="relative flex-1">
            <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Type an address or beach, then press Enter"
              className="w-full rounded-xl bg-white/10 py-2 pr-3 pl-9 text-sm placeholder:text-slate-500 focus:ring-2 focus:ring-teal-300 focus:outline-none"
              aria-label="Address or beach"
            />
          </div>
          <button type="submit" className="rounded-xl bg-teal-400 px-4 py-2 text-sm font-semibold text-navy-900 hover:bg-teal-300">
            Check
          </button>
        </form>
        <nav className="flex overflow-hidden rounded-xl ring-1 ring-white/15">
          <button
            type="button"
            onClick={() => setMode('spot')}
            className={`flex items-center gap-1 px-3 py-2 text-sm ${mode === 'spot' ? 'bg-white/15 font-semibold' : 'hover:bg-white/10'}`}
          >
            <MapPin size={14} /> Check a spot
          </button>
          {FEATURES.nearMe ? (
            <button
              type="button"
              onClick={() => setMode('near')}
              className={`flex items-center gap-1 px-3 py-2 text-sm ${mode === 'near' ? 'bg-white/15 font-semibold' : 'hover:bg-white/10'}`}
            >
              <Navigation size={14} /> Near me
            </button>
          ) : (
            <span className="flex cursor-not-allowed items-center gap-1 px-3 py-2 text-sm text-slate-500" title="Find water near me is not finished yet">
              <Navigation size={14} /> Near me (coming soon)
            </span>
          )}
        </nav>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`flex items-center gap-1 rounded-full px-2.5 py-1 font-semibold ${statusBadge ? 'bg-amber-400/20 text-amber-200' : 'bg-emerald-400/15 text-emerald-200'}`}
            title="Key O toggles offline mode"
          >
            {statusBadge ? <WifiOff size={13} /> : <Wifi size={13} />}
            {health?.demo_mode ? 'Demo · Cached' : offline ? 'Cached' : 'Live'}
          </span>
          <span
            className={`flex items-center gap-1 rounded-full px-2.5 py-1 ${health?.gemma_configured ? 'bg-teal-400/15 text-teal-100' : 'bg-slate-500/20 text-slate-300'}`}
            title={health?.gemma_configured ? `Gemma model: ${health.gemma_model}` : 'Add GEMINI_API_KEY to backend/.env'}
          >
            <Sparkles size={12} /> Gemma {health?.gemma_configured ? 'on' : 'off'}
          </span>
        </div>
      </header>

      {bootError && (
        <div className="px-4">
          <ErrorBox message={bootError} />
        </div>
      )}

      <main className="grid min-h-0 flex-1 gap-3 px-4 pb-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(380px,1fr)]">
        <div className="relative min-h-[380px]">
          <MapView
            center={center}
            zoom={zoom}
            spots={mapSpots}
            selectedId={mode === 'spot' && spot ? 'selected' : null}
            gibsDate={report?.imagery.date ?? yesterdayUtc()}
            chlTime={report?.chlorophyll.overlay_time ?? null}
            lens={lens}
            scanning={scanning}
            offline={offline}
            ring={mode === 'near' && origin && config ? { lat: origin.lat, lon: origin.lon, km: driveMin * config.max_km_per_min } : null}
            origin={mode === 'near' ? origin : null}
            onSpotClick={onSpotClick}
            onMapClick={mode === 'near' ? setPin : undefined}
          />
          <div className="glass-strong absolute bottom-4 left-4 z-[600] w-64 rounded-xl p-3 text-xs">
            <label className="flex items-center justify-between gap-2 font-semibold text-teal-100">
              <span className="flex items-center gap-1">
                <Layers size={13} /> Color lens
              </span>
              <span className="text-slate-400">{Math.round(lens * 100)}% chlorophyll</span>
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={lens}
              onChange={(e) => setLens(Number(e.target.value))}
              className="lens mt-2 w-full"
              aria-label="Blend satellite photo and chlorophyll overlay"
              disabled={!report?.chlorophyll.overlay_time}
            />
            <div className="mt-1 flex justify-between text-[10px] text-slate-400">
              <span>Satellite photo</span>
              <span>Chlorophyll</span>
            </div>
            {!report && <p className="mt-1 text-[10px] text-slate-500">Open a report to enable the chlorophyll layer.</p>}
          </div>
          {FEATURES.presentationKeys && (
            <div className="glass-strong absolute top-4 right-4 z-[600] rounded-xl px-3 py-2 text-[11px] text-slate-300">
              <kbd className="rounded bg-white/10 px-1">P</kbd> demo beaches · <kbd className="rounded bg-white/10 px-1">O</kbd> offline
            </div>
          )}
        </div>

        <aside className="min-h-0 overflow-y-auto pr-1">
          <AnimatePresence mode="wait">
            {mode === 'near' ? (
              <motion.div key="near" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
                <NearbyPanel
                  driveOptions={config?.drive_options ?? [15, 30, 60]}
                  driveMin={driveMin}
                  onDriveMin={changeDrive}
                  origin={origin}
                  onLocate={locate}
                  locating={locating}
                  result={filteredNearby}
                  loading={nearbyLoading}
                  error={nearbyError}
                  onRetry={() => origin && loadNearby(origin, driveMin)}
                  onOpen={(s) => openSpot({ name: s.name, lat: s.lat, lon: s.lon, kind: s.kind })}
                  onAsk={ask}
                  askLoading={askLoading}
                  askNote={askNote}
                />
              </motion.div>
            ) : (
              <motion.div key="spot" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="space-y-3">
                {searchLoading && <Loading label="Looking up that place…" />}
                {searchError && <ErrorBox message={searchError} />}
                {search && <CandidatePicker search={search} onPick={(c) => openSpot(c)} />}
                {reportLoading && <Loading label="Reading satellite passes and official status…" />}
                {reportError && <ErrorBox message={reportError} onRetry={spot ? () => openSpot(spot) : undefined} />}
                {report && !reportLoading && (
                  <ReportPanel report={report} insights={insights} insightsLoading={insightsLoading} insightsError={insightsError} voice={voice} />
                )}
                {!search && !searchLoading && !report && !reportLoading && !reportError && (
                  <Empty title="Check a spot">
                    Type an address or beach above, click a pin, or press <strong>P</strong> to cycle the demo beaches
                    {config ? ` (${config.demo_beaches.map((b) => b.name).join(', ')})` : ''}.
                  </Empty>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </aside>
      </main>
    </div>
  )
}

function CandidatePicker({ search, onPick }: { search: SearchResult; onPick: (c: Candidate) => void }) {
  const { place, candidates } = search
  return (
    <section className="glass-strong rounded-2xl p-4">
      {place ? (
        <p className="text-xs text-slate-400">
          Found: <span className="text-slate-200">{place.name}</span>
        </p>
      ) : (
        <p className="text-sm text-slate-300">No place found for “{search.query}”. Try a fuller address.</p>
      )}
      {search.warnings.map((w, i) => (
        <p key={i} className="mt-1 text-xs text-amber-200">
          {w}
        </p>
      ))}
      {place && candidates.length === 0 && (
        <div className="mt-2 space-y-2 text-sm text-slate-300">
          <p>No named beach or coastal cliff within a few km.</p>
          <button
            type="button"
            onClick={() => onPick({ ...place, kind: 'place' })}
            className="rounded-lg bg-white/10 px-3 py-1.5 text-xs hover:bg-white/15"
          >
            Check this exact point anyway
          </button>
        </div>
      )}
      {candidates.length === 1 && (
        <div className="mt-2">
          <p className="text-sm text-slate-200">
            We found <strong>{candidates[0].name}</strong> ({candidates[0].kind}, {candidates[0].distance_km.toFixed(1)} km away). Is this the one?
          </p>
          <button
            type="button"
            onClick={() => onPick(candidates[0])}
            className="mt-2 rounded-lg bg-teal-400 px-3 py-1.5 text-sm font-semibold text-navy-900 hover:bg-teal-300"
          >
            Yes, check it
          </button>
        </div>
      )}
      {candidates.length > 1 && (
        <div className="mt-2">
          <p className="text-sm text-slate-200">Several spots are nearby. Pick one:</p>
          <ul className="mt-2 space-y-1">
            {candidates.map((c) => (
              <li key={`${c.name}-${c.lat}`}>
                <button
                  type="button"
                  onClick={() => onPick(c)}
                  className="flex w-full items-center justify-between rounded-lg bg-white/5 px-3 py-2 text-left text-sm hover:bg-white/10"
                >
                  <span>{c.name}</span>
                  <span className="text-xs text-slate-400">
                    {c.kind} · {c.distance_km.toFixed(1)} km
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-2 text-[10px] text-slate-500">{search.attribution}</p>
    </section>
  )
}
