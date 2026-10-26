import { ChevronRight, Thermometer } from 'lucide-react'
import { kmToMi } from '../format'
import { kindColor, theme } from '../theme'
import type { NearbyResult, WaterBody } from '../types'
import { Empty, ErrorBox, HaloBadge, Loading } from './common'

interface Props {
  result: NearbyResult | null
  radiusMi: number | null
  loading: boolean
  error: string | null
  onRetry: () => void
  highlightId: string | null
  onHover: (id: string | null) => void
  onSelect: (body: WaterBody) => void
}

const PLURAL: Record<string, string> = { beach: 'beaches', bay: 'bays', estuary: 'estuaries' }

function plural(kind: string, n: number): string {
  return n === 1 ? kind : (PLURAL[kind] ?? `${kind}s`)
}

export default function NearbyPanel(p: Props) {
  if (p.loading) {
    return <Loading label="Finding beaches, bays, rivers, and lakes… The first search of a new area can take up to 45 seconds." />
  }
  if (p.error) return <ErrorBox message={p.error} onRetry={p.onRetry} />
  if (!p.result) {
    return (
      <Empty title="Search nearby">
        Enter a starting address and a radius in miles above, then press <strong>Search nearby</strong>. The map shows the circle and highlights every
        named body of water inside it.
      </Empty>
    )
  }

  const { result } = p
  // Only water bodies with data go in the list. The others show on the map in gray.
  const withData = result.spots.filter((s) => s.report_available)
  const noData = result.spots.length - withData.length
  const counts = new Map<string, number>()
  for (const s of withData) counts.set(s.kind, (counts.get(s.kind) ?? 0) + 1)

  return (
    <div className="space-y-3">
      <section className="glass-strong space-y-2 rounded-2xl p-4">
        <h2 className="text-xl leading-7 font-bold text-white">
          {withData.length} {withData.length === 1 ? 'body' : 'bodies'} of water with data within {p.radiusMi ?? kmToMi(result.radius_km)} mi
        </h2>
        <p className="text-xs text-slate-400">From {result.origin.name}</p>
        {counts.size > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {[...counts].map(([kind, n]) => (
              <li key={kind} className="flex items-center gap-1.5 rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-300">
                <span className="h-2 w-2 rounded-full" style={{ background: kindColor(kind) }} />
                {n} {plural(kind, n)}
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-slate-400">Click a row or a shape on the map to open its water report.</p>
        {noData > 0 && (
          <p className="flex items-center gap-1.5 text-xs text-slate-400">
            <span className="h-3 w-3 shrink-0 rounded-sm border border-dashed bg-slate-400/25" style={{ borderColor: theme.noData }} aria-hidden />
            {noData} more {noData === 1 ? 'body' : 'bodies'} of water (lakes, rivers) have no data. They show in gray on the map and cannot be opened.
          </p>
        )}
      </section>

      {result.warnings.map((w, i) => (
        <p key={i} className="rounded-lg bg-amber-400/10 p-2 text-xs text-amber-100">
          {w}
        </p>
      ))}

      {withData.length === 0 ? (
        <Empty title={`No water with data within ${p.radiusMi ?? kmToMi(result.radius_km)} mi`}>
          Water data covers ocean beaches and bays. Try a larger radius or an address nearer the coast.
        </Empty>
      ) : (
        <ul className="space-y-1.5" onMouseLeave={() => p.onHover(null)}>
          {withData.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => p.onSelect(s)}
                onMouseEnter={() => p.onHover(s.id)}
                onFocus={() => p.onHover(s.id)}
                className={`glass flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left hover:bg-white/10 ${p.highlightId === s.id ? 'ring-2 ring-sky-300/70' : ''}`}
              >
                <span className="flex min-w-0 items-center gap-2.5">
                  <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: kindColor(s.kind) }} aria-hidden />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-white">{s.name}</span>
                    <span className="flex items-center gap-1 text-xs text-slate-400">
                      {s.kind} · {kmToMi(s.distance_km)} mi away
                      {s.sea_temp_f !== null && (
                        <>
                          {' · '}
                          <Thermometer size={11} /> {Math.round(s.sea_temp_f)} °F
                        </>
                      )}
                    </span>
                  </span>
                </span>
                {s.halo ? <HaloBadge halo={s.halo} /> : <ChevronRight size={16} className="shrink-0 text-slate-400" />}
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-slate-400">{result.attribution}</p>
    </div>
  )
}
