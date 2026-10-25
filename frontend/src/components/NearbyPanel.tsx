import { Car, LocateFixed, Sparkles } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import type { NearbyResult, NearbySpot } from '../types'
import { Empty, ErrorBox, HaloBadge, Loading } from './common'

interface Props {
  driveOptions: number[]
  driveMin: number
  onDriveMin: (m: number) => void
  origin: { lat: number; lon: number } | null
  onLocate: () => void
  locating: boolean
  result: NearbyResult | null
  loading: boolean
  error: string | null
  onRetry: () => void
  onOpen: (spot: NearbySpot) => void
  onAsk: (query: string) => void
  askLoading: boolean
  askNote: string | null
}

export default function NearbyPanel(p: Props) {
  const [question, setQuestion] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (question.trim().length > 2) p.onAsk(question.trim())
  }
  return (
    <div className="space-y-3">
      <section className="glass-strong space-y-3 rounded-2xl p-4">
        <h2 className="text-lg font-bold text-white">Find water near me</h2>
        <p className="text-xs text-slate-400">Click the map to drop a pin, or use your location. Then pick a drive time.</p>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={p.onLocate}
            className="flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-sm hover:bg-white/15"
          >
            <LocateFixed size={14} /> {p.locating ? 'Locating…' : 'Use my location'}
          </button>
          <div className="flex overflow-hidden rounded-lg ring-1 ring-white/15" role="radiogroup" aria-label="Drive time">
            {p.driveOptions.map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={p.driveMin === m}
                onClick={() => p.onDriveMin(m)}
                className={`px-3 py-1.5 text-sm ${p.driveMin === m ? 'bg-teal-400 font-semibold text-navy-900' : 'bg-white/5 hover:bg-white/10'}`}
              >
                {m} min
              </button>
            ))}
          </div>
        </div>
        <form onSubmit={submit} className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder='Ask Gemma: "warm water within 30 min of UCSD"'
            className="flex-1 rounded-lg bg-white/10 px-3 py-2 text-sm placeholder:text-slate-500 focus:ring-2 focus:ring-teal-300 focus:outline-none"
            aria-label="Natural language search"
          />
          <button type="submit" disabled={p.askLoading} className="flex items-center gap-1 rounded-lg bg-teal-400/90 px-3 text-sm font-semibold text-navy-900 disabled:opacity-60">
            <Sparkles size={14} /> {p.askLoading ? '…' : 'Ask'}
          </button>
        </form>
        {p.askNote && <p className="text-xs text-teal-100">{p.askNote}</p>}
      </section>

      {!p.origin && !p.loading && <Empty title="No search center yet">Drop a pin on the map or use your location.</Empty>}
      {p.loading && <Loading label="Finding beaches and cliffs in range…" />}
      {p.error && !p.loading && <ErrorBox message={p.error} onRetry={p.onRetry} />}
      {p.result && !p.loading && (
        <section className="space-y-2">
          {p.result.warnings.map((w, i) => (
            <p key={i} className="rounded-lg bg-amber-400/10 p-2 text-xs text-amber-100">
              {w}
            </p>
          ))}
          {p.result.spots.length === 0 ? (
            <Empty title={`Nothing within ${p.result.drive_min} minutes`}>Try a longer drive time or move the pin closer to the coast.</Empty>
          ) : (
            <>
              <p className="text-xs text-slate-400">
                {p.result.spots.length} spots within {p.result.drive_min} min. Click one for the full report.
              </p>
              <ul className="space-y-1.5">
                {p.result.spots.map((s) => (
                  <li key={`${s.name}-${s.lat}-${s.lon}`}>
                    <button
                      type="button"
                      onClick={() => p.onOpen(s)}
                      className="glass flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left hover:bg-white/10"
                    >
                      <span>
                        <span className="block text-sm font-semibold text-white">{s.name}</span>
                        <span className="flex items-center gap-1 text-[11px] text-slate-400">
                          <Car size={11} /> {Math.round(s.drive_min)} min ({s.drive_method === 'osrm' ? 'OSRM route' : 'straight-line estimate'}) · {s.kind}
                          {s.sea_temp_f !== null && ` · ${Math.round(s.sea_temp_f)} °F`}
                        </span>
                      </span>
                      <HaloBadge halo={s.halo} />
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="text-[10px] text-slate-500">{p.result.attribution}</p>
        </section>
      )}
    </div>
  )
}
