import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeft, Layers, MapPin, Ruler, Search, Sparkles, Waves, Wifi, WifiOff } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { api, setOffline as setApiOffline } from './api'
import { ErrorBox, Loading } from './components/common'
import MapView, { type MapSpot, type MapTarget } from './components/MapView'
import NearbyPanel from './components/NearbyPanel'
import ReportPanel from './components/ReportPanel'
import { FEATURES } from './features'
import type { AppConfig, BeachReport, Health, Insights, NearbyResult, WaterBody } from './types'

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
  const [mode, setMode] = useState<Mode>('near')
  const [offline, setOffline] = useState(false)

  const [spot, setSpot] = useState<SpotRef | null>(null)
  const [report, setReport] = useState<BeachReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)
  const [insights, setInsights] = useState<Insights | null>(null)
  const [insightsLoading, setInsightsLoading] = useState(false)
  const [insightsError, setInsightsError] = useState<string | null>(null)

  const [target, setTarget] = useState<MapTarget>({ center: DEFAULT_CENTER, zoom: 11 })
  const [lens, setLens] = useState(0)

  const [address, setAddress] = useState('')
  const [radiusInput, setRadiusInput] = useState('')
  const [lastSearch, setLastSearch] = useState<{ address: string; radiusMi: number } | null>(null)
  const [nearby, setNearby] = useState<NearbyResult | null>(null)
  const [nearbyLoading, setNearbyLoading] = useState(false)
  const [nearbyError, setNearbyError] = useState<string | null>(null)
  const [selectedWaterId, setSelectedWaterId] = useState<string | null>(null)
  const [hoverId, setHoverId] = useState<string | null>(null)
  const highlightId = hoverId ?? selectedWaterId

  const presentationIndex = useRef(-1)
  const reportAbort = useRef<AbortController | null>(null)
  const nearbyAbort = useRef<AbortController | null>(null)

  const refreshStatus = useCallback(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
    api.voiceStatus().then(setVoice).catch(() => setVoice(null))
  }, [])

  const openSpot = useCallback(async (target: SpotRef, zoomOverride?: number) => {
    reportAbort.current?.abort()
    const ctrl = new AbortController()
    reportAbort.current = ctrl
    setMode('spot')
    setSpot(target)
    setTarget({ center: [target.lat, target.lon], zoom: Math.min(16, Math.max(3, zoomOverride ?? 14)) })
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

  const closeSpot = useCallback(() => {
    reportAbort.current?.abort()
    setSpot(null)
    setReport(null)
    setReportError(null)
    setReportLoading(false)
    setInsights(null)
    setInsightsLoading(false)
  }, [])

  useEffect(() => {
    api
      .config()
      .then((c) => {
        setConfig(c)
        const p = new URLSearchParams(window.location.search)
        const lat = Number(p.get('lat'))
        const lon = Number(p.get('lon'))
        const zoomParam = Number(p.get('zoom'))
        if (p.has('lat') && p.has('lon') && Number.isFinite(lat) && Number.isFinite(lon)) {
          openSpot(
            { name: p.get('name') ?? 'Selected spot', lat, lon, kind: p.get('kind') ?? 'beach' },
            p.has('zoom') && Number.isInteger(zoomParam) ? zoomParam : undefined,
          )
        }
      })
      .catch((e) => setBootError(`Backend not reachable: ${errMsg(e)}. Start it with uvicorn (see README).`))
    refreshStatus()
    const t = setInterval(refreshStatus, 15000)
    return () => clearInterval(t)
  }, [refreshStatus, openSpot])

  const runNearby = useCallback(
    async (addr: string, radiusMi: number) => {
      nearbyAbort.current?.abort()
      const ctrl = new AbortController()
      nearbyAbort.current = ctrl
      closeSpot()
      setMode('near')
      setLastSearch({ address: addr, radiusMi })
      setNearby(null)
      setNearbyError(null)
      setSelectedWaterId(null)
      setHoverId(null)
      setNearbyLoading(true)
      try {
        const res = await api.nearby(addr, radiusMi, ctrl.signal)
        setNearby(res)
        setTarget({ circle: { lat: res.origin.lat, lon: res.origin.lon, km: res.radius_km } })
      } catch (e) {
        if (!ctrl.signal.aborted) setNearbyError(errMsg(e))
      } finally {
        if (!ctrl.signal.aborted) setNearbyLoading(false)
      }
    },
    [closeSpot],
  )

  // The browser checks required, min, and max before this runs.
  const submitNearby = (e: FormEvent) => {
    e.preventDefault()
    const addr = address.trim()
    const radiusMi = Number(radiusInput)
    if (addr.length < 2 || !Number.isFinite(radiusMi)) return
    runNearby(addr, radiusMi)
  }

  const selectWater = (b: WaterBody) => {
    setSelectedWaterId(b.id)
    if (b.report_available) openSpot({ name: b.name, lat: b.lat, lon: b.lon, kind: b.kind }, 13)
    else setTarget({ geometry: b.geometry })
  }

  const backToResults = () => {
    closeSpot()
    setMode('near')
    if (nearby) setTarget({ circle: { lat: nearby.origin.lat, lon: nearby.origin.lon, km: nearby.radius_km } })
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

  const mapSpots: MapSpot[] = useMemo(
    () => (mode === 'spot' && spot ? [{ id: 'selected', name: spot.name, lat: spot.lat, lon: spot.lon, halo: report?.halo ?? null }] : []),
    [mode, spot, report],
  )

  const scanning = reportLoading || nearbyLoading
  const statusBadge = offline || health?.demo_mode
  const minMi = config?.nearby_min_mi ?? 0.5
  const maxMi = config?.nearby_max_mi ?? 25

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
        <form onSubmit={submitNearby} className="flex min-w-[280px] flex-1 flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-[3]">
            <MapPin size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-slate-400" />
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              required
              minLength={2}
              maxLength={200}
              placeholder="Enter a starting address"
              className="w-full rounded-xl bg-white/10 py-2 pr-3 pl-9 text-sm placeholder:text-slate-500 focus:ring-2 focus:ring-teal-300 focus:outline-none"
              aria-label="Starting address"
            />
          </div>
          <div className="relative w-52 flex-none">
            <Ruler size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-slate-400" />
            <input
              type="number"
              inputMode="decimal"
              step="any"
              min={minMi}
              max={maxMi}
              required
              value={radiusInput}
              onChange={(e) => setRadiusInput(e.target.value)}
              placeholder="Radius in miles"
              title={`Search radius: ${minMi} to ${maxMi} miles`}
              className="w-full rounded-xl bg-white/10 py-2 pr-9 pl-9 text-sm placeholder:text-slate-500 focus:ring-2 focus:ring-teal-300 focus:outline-none"
              aria-label="Search radius in miles"
            />
            <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs text-slate-400">mi</span>
          </div>
          <button
            type="submit"
            disabled={nearbyLoading}
            className="flex items-center gap-1.5 rounded-xl bg-teal-400 px-4 py-2 text-sm font-semibold text-navy-900 hover:bg-teal-300 disabled:opacity-60"
          >
            <Search size={15} /> Search nearby
          </button>
        </form>
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
            target={target}
            spots={mapSpots}
            selectedId={mode === 'spot' && spot ? 'selected' : null}
            gibsDate={report?.imagery.date ?? yesterdayUtc()}
            chlTime={report?.chlorophyll.overlay_time ?? null}
            lens={lens}
            scanning={scanning}
            offline={offline}
            circle={nearby ? { lat: nearby.origin.lat, lon: nearby.origin.lon, km: nearby.radius_km } : null}
            origin={nearby?.origin ?? null}
            water={nearby?.spots ?? []}
            highlightId={highlightId}
            onWaterClick={selectWater}
            onWaterHover={setHoverId}
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
              aria-label="Blend imagery and chlorophyll overlay"
              disabled={!report?.chlorophyll.overlay_time}
            />
            <div className="mt-1 flex justify-between text-[10px] text-slate-400">
              <span>Imagery</span>
              <span>Chlorophyll</span>
            </div>
            {!report && <p className="mt-1 text-[10px] text-slate-500">Open a beach or bay report to enable the chlorophyll layer.</p>}
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
                  result={nearby}
                  radiusMi={lastSearch?.radiusMi ?? null}
                  loading={nearbyLoading}
                  error={nearbyError}
                  onRetry={() => lastSearch && runNearby(lastSearch.address, lastSearch.radiusMi)}
                  highlightId={highlightId}
                  onHover={setHoverId}
                  onSelect={selectWater}
                />
              </motion.div>
            ) : (
              <motion.div key="spot" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="space-y-3">
                <button type="button" onClick={backToResults} className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm text-teal-100 hover:bg-white/10">
                  <ArrowLeft size={15} /> {nearby ? `Back to ${nearby.spots.length} results` : 'Search nearby'}
                </button>
                {reportLoading && <Loading label="Reading satellite passes and official status…" />}
                {reportError && <ErrorBox message={reportError} onRetry={spot ? () => openSpot(spot) : undefined} />}
                {report && !reportLoading && (
                  <ReportPanel report={report} insights={insights} insightsLoading={insightsLoading} insightsError={insightsError} voice={voice} />
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </aside>
      </main>
    </div>
  )
}
