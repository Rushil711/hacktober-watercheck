import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeft, MapPin, Ruler, Search, Sparkles, Waves, Wifi, WifiOff } from 'lucide-react'
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
  const [sheetOpen, setSheetOpen] = useState(false) // phone bottom sheet

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
    setSheetOpen(true)
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

  // Only water bodies with data are clickable (list rows and map shapes).
  const selectWater = (b: WaterBody) => {
    if (!b.report_available) return
    setSelectedWaterId(b.id)
    openSpot({ name: b.name, lat: b.lat, lon: b.lon, kind: b.kind }, 13)
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
      <header className="flex items-center gap-2 px-3 py-2 sm:gap-3 sm:px-4 sm:py-3">
        <div className="flex shrink-0 items-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-teal-400/15 text-teal-200">
            <Waves size={20} aria-hidden />
          </div>
          <div className="sr-only md:not-sr-only">
            <h1 className="text-xl leading-6 font-bold text-white">WaterCheck</h1>
            <p className="text-xs text-slate-300">Satellite + official data · explained by Gemma</p>
          </div>
        </div>
        <form onSubmit={submitNearby} className="flex min-w-0 flex-1 items-center gap-2" role="search">
          <div className="relative min-w-0 flex-1">
            <MapPin size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-300" aria-hidden />
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              required
              minLength={2}
              maxLength={200}
              placeholder="Enter a starting address"
              className="h-10 w-full rounded-xl bg-white/10 pr-3 pl-9 text-sm placeholder:text-slate-400 focus:ring-2 focus:ring-teal-300 focus:outline-none"
              aria-label="Starting address"
            />
          </div>
          <div className="relative w-24 shrink-0 sm:w-40">
            <Ruler size={15} className="pointer-events-none absolute top-1/2 left-3 hidden -translate-y-1/2 text-slate-300 sm:block" aria-hidden />
            <input
              type="number"
              inputMode="decimal"
              step="any"
              min={minMi}
              max={maxMi}
              required
              value={radiusInput}
              onChange={(e) => setRadiusInput(e.target.value)}
              placeholder="Radius"
              title={`Search radius: ${minMi} to ${maxMi} miles`}
              className="h-10 w-full rounded-xl bg-white/10 pr-8 pl-3 text-sm placeholder:text-slate-400 focus:ring-2 focus:ring-teal-300 focus:outline-none sm:pl-9"
              aria-label="Search radius in miles"
            />
            <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs text-slate-300" aria-hidden>
              mi
            </span>
          </div>
          <button
            type="submit"
            disabled={nearbyLoading}
            aria-label="Search nearby"
            className="flex h-10 shrink-0 items-center gap-1.5 rounded-xl bg-teal-400 px-3 text-sm font-semibold text-navy-900 hover:bg-teal-300 disabled:opacity-60 sm:px-4"
          >
            <Search size={16} aria-hidden /> <span className="hidden sm:inline">Search nearby</span>
          </button>
        </form>
        <div className="hidden items-center gap-2 text-xs lg:flex">
          <span
            className={`flex items-center gap-1 rounded-full px-2.5 py-1 font-semibold ${statusBadge ? 'bg-amber-400/20 text-amber-200' : 'bg-emerald-400/15 text-emerald-200'}`}
            title="Key O toggles offline mode"
          >
            {statusBadge ? <WifiOff size={13} aria-hidden /> : <Wifi size={13} aria-hidden />}
            {health?.demo_mode ? 'Demo · Cached' : offline ? 'Cached' : 'Live'}
          </span>
          <span
            className={`flex items-center gap-1 rounded-full px-2.5 py-1 ${health?.gemma_configured ? 'bg-teal-400/15 text-teal-100' : 'bg-slate-500/20 text-slate-200'}`}
            title={health?.gemma_configured ? `Gemma model: ${health.gemma_model}` : 'Add GEMINI_API_KEY to backend/.env'}
          >
            <Sparkles size={12} aria-hidden /> Gemma {health?.gemma_configured ? 'on' : 'off'}
          </span>
        </div>
      </header>

      {bootError && (
        <div className="px-3 pb-2 sm:px-4">
          <ErrorBox message={bootError} />
        </div>
      )}

      {/* Phone: the map fills the screen and the panel is a bottom sheet. Desktop (lg): two columns. */}
      <main className="relative min-h-0 flex-1 lg:grid lg:grid-cols-[minmax(0,1.25fr)_minmax(380px,1fr)] lg:gap-3 lg:px-4 lg:pb-4">
        <div className="absolute inset-0 lg:relative lg:inset-auto lg:min-h-[380px]">
          <MapView
            target={target}
            spots={mapSpots}
            selectedId={mode === 'spot' && spot ? 'selected' : null}
            gibsDate={report?.imagery.date ?? yesterdayUtc()}
            scanning={scanning}
            offline={offline}
            circle={nearby ? { lat: nearby.origin.lat, lon: nearby.origin.lon, km: nearby.radius_km } : null}
            origin={nearby?.origin ?? null}
            water={nearby?.spots ?? []}
            highlightId={highlightId}
            onWaterClick={selectWater}
            onWaterHover={setHoverId}
          />
          {FEATURES.presentationKeys && (
            <div className="glass-strong absolute top-14 right-3 z-[600] rounded-xl px-3 py-2 text-xs text-slate-300">
              <kbd className="rounded bg-white/10 px-1">P</kbd> demo beaches · <kbd className="rounded bg-white/10 px-1">O</kbd> offline
            </div>
          )}
        </div>

        <aside
          className={`absolute inset-x-0 bottom-0 z-[700] flex flex-col rounded-t-2xl border-t border-white/10 bg-navy-900 transition-[height] duration-200 lg:static lg:z-auto lg:h-auto lg:min-h-0 lg:rounded-none lg:border-0 lg:bg-transparent ${sheetOpen ? 'h-[72%]' : 'h-[40%]'}`}
          aria-label="Results"
        >
          <button
            type="button"
            onClick={() => setSheetOpen((o) => !o)}
            aria-expanded={sheetOpen}
            aria-controls="panel"
            aria-label={sheetOpen ? 'Make the panel smaller' : 'Make the panel larger'}
            className="flex h-7 w-full shrink-0 items-center justify-center lg:hidden"
          >
            <span className="h-1 w-10 rounded-full bg-slate-400" />
          </button>
          <div id="panel" className="min-h-0 flex-1 overflow-y-auto px-3 pb-4 lg:px-0 lg:pr-1 lg:pb-0">
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
                    <ArrowLeft size={15} aria-hidden /> {nearby ? `Back to ${nearby.spots.filter((b) => b.report_available).length} results` : 'Search nearby'}
                  </button>
                  {reportLoading && <Loading label="Reading satellite passes and official status…" />}
                  {reportError && <ErrorBox message={reportError} onRetry={spot ? () => openSpot(spot) : undefined} />}
                  {report && !reportLoading && (
                    <ReportPanel report={report} insights={insights} insightsLoading={insightsLoading} insightsError={insightsError} voice={voice} />
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </aside>
      </main>
    </div>
  )
}
