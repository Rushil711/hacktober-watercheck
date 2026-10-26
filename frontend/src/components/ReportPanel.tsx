import { motion } from 'framer-motion'
import {
  Clock,
  Droplets,
  Info,
  LoaderCircle,
  Mountain,
  Satellite,
  ShieldAlert,
  Sparkles,
  Sun,
  Thermometer,
  Volume2,
  Waves,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { FEATURES } from '../features'
import { fmtTime } from '../format'
import { officialStyle } from '../theme'
import type { BeachReport, Insights, SkillResult } from '../types'
import { CachedBadge, Card, ErrorBox, HaloBadge, Loading, ReceiptButton } from './common'
import { BestTimeStrip, ChlTrend, FeelGauge, JumpMeter } from './visuals'

interface Props {
  report: BeachReport
  insights: Insights | null
  insightsLoading: boolean
  insightsError: string | null
  voice: { configured: boolean; problem: string | null; docs_url: string } | null
}

function GemmaUnavailable({ result }: { result: SkillResult<unknown> }) {
  return (
    <p className="text-xs text-slate-400">
      Gemma card hidden: {result.error ?? 'no valid reply'}. The data above is unchanged.
    </p>
  )
}

function OfficialCard({ report }: { report: BeachReport }) {
  const o = report.official
  const style = officialStyle[o.status]
  return (
    <Card title="Official status" icon={<ShieldAlert size={14} />} right={<CachedBadge cached={o.receipt.cached} />}>
      <div className={`rounded-xl p-3 ring-1 ${style.ring} ${style.tone}`}>
        <ReceiptButton receipt={o.receipt}>
          <span className="text-2xl font-bold">{o.label}</span>
        </ReceiptButton>
        {style.note && <p className="mt-1 text-xs font-medium opacity-90">{style.note}</p>}
        <p className="mt-2 text-sm opacity-90">{o.detail}</p>
        {o.station && (
          <p className="mt-1 text-xs opacity-75">
            Station {o.station.id ?? ''} · {o.station.name} · {o.station.distance_km.toFixed(2)} km away
          </p>
        )}
        {o.events.length > 0 && (
          <ul className="mt-2 space-y-1 text-xs">
            {o.events.map((e, i) => (
              <li key={i} className="rounded-lg bg-black/20 p-2">
                <span className="font-semibold capitalize">{e.type}</span> issued {fmtTime(e.issued_at)}
                {e.description && <span className="block opacity-80">{e.description}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="mt-2 text-xs text-slate-400">This status comes from the water-quality service. Gemma never sets it.</p>
    </Card>
  )
}

function ExplainCard({ insights, loading, error }: { insights: Insights | null; loading: boolean; error: string | null }) {
  const explain = insights?.explain
  return (
    <Card
      title="Gemma explains the evidence"
      icon={<Sparkles size={14} />}
      right={explain?.ok ? <span className="text-xs text-slate-400">{explain.model}{explain.cached ? ' · cached' : ''}</span> : null}
    >
      {loading && <Loading label="Gemma is reading the evidence…" />}
      {error && !loading && <ErrorBox message={error} />}
      {explain && !explain.ok && <GemmaUnavailable result={explain} />}
      {explain?.ok && explain.data && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-3 text-sm">
          <p className="text-lg font-semibold text-white">{explain.data.headline}</p>
          <p className="text-slate-200">{explain.data.environmental_summary}</p>
          {(
            [
              ['Key observations', explain.data.key_observations],
              ['Concerns', explain.data.concerns],
              ['Limitations', explain.data.limitations],
              ['Recommended next steps', explain.data.recommended_next_steps],
            ] as const
          ).map(([title, items]) =>
            items.length ? (
              <div key={title}>
                <p className="text-xs font-semibold tracking-wider text-teal-200/80 uppercase">{title}</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-slate-300">
                  {items.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              </div>
            ) : null,
          )}
          {explain.data.sources_used.length > 0 && (
            <p className="text-xs text-slate-400">Sources: {explain.data.sources_used.join(' · ')}</p>
          )}
        </motion.div>
      )}
    </Card>
  )
}

function VoiceButton({ report, insights, voice }: { report: BeachReport; insights: Insights | null; voice: Props['voice'] }) {
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl)
    },
    [audioUrl],
  )
  const configured = voice?.configured ?? false
  const play = async () => {
    setState('loading')
    setError(null)
    try {
      const blob = await api.voiceBriefing(report, insights)
      setAudioUrl(URL.createObjectURL(blob))
      setState('ready')
    } catch (e) {
      setState('error')
      setError(e instanceof Error ? e.message : 'Voice briefing failed')
    }
  }
  return (
    <div className="glass flex flex-col gap-1 rounded-2xl p-3">
      <button
        type="button"
        onClick={play}
        disabled={!configured || state === 'loading'}
        className="flex items-center justify-center gap-2 rounded-xl bg-teal-400/90 px-4 py-2.5 text-sm font-semibold text-navy-900 transition hover:bg-teal-300 disabled:cursor-not-allowed disabled:bg-slate-600/60 disabled:text-slate-300"
      >
        {state === 'loading' ? <LoaderCircle className="animate-spin" size={16} /> : <Volume2 size={16} />}
        {state === 'loading' ? 'Grok is recording the briefing…' : 'Play Grok Voice briefing'}
      </button>
      {audioUrl && <audio ref={audioRef} src={audioUrl} controls autoPlay className="mt-1 w-full" aria-label="Grok Voice briefing" />}
      {!configured && (
        <p className="text-xs text-slate-400">
          {voice?.problem ?? 'Grok Voice is not configured.'}{' '}
          <a className="text-teal-300 underline" href={voice?.docs_url} target="_blank" rel="noreferrer">
            Docs
          </a>
        </p>
      )}
      {error && <p className="text-xs text-rose-300">{error}</p>}
    </div>
  )
}

export default function ReportPanel({ report, insights, insightsLoading, insightsError, voice }: Props) {
  const chl = report.chlorophyll
  const verdicts = insights?.verdicts
  const best = insights?.best_hours
  return (
    <div className="space-y-3">
      <header className="glass-strong rounded-2xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-2xl font-bold text-white">{report.spot.name}</h2>
          <HaloBadge halo={report.halo} />
        </div>
        <p className="mt-1 text-xs text-slate-400">
          {report.spot.lat.toFixed(4)}, {report.spot.lon.toFixed(4)} · {report.spot.kind} · built {fmtTime(report.generated_at)}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-slate-300">
            <Clock size={12} /> Data age: {report.data_age}
          </span>
          <ReceiptButton receipt={report.imagery.receipt} className="text-slate-300">
            <span className="flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5">
              <Satellite size={12} /> Satellite photo: {report.imagery.date ?? 'Unavailable'}
            </span>
          </ReceiptButton>
          {report.offline && (
            <span className="rounded-full bg-amber-400/20 px-2 py-0.5 font-semibold text-amber-200">Cached · offline mode</span>
          )}
        </div>
        {report.halo.reasons.length > 0 && <p className="mt-2 text-xs text-slate-300">Halo: {report.halo.reasons.join(' · ')}</p>}
      </header>

      {report.warnings.length > 0 && (
        <div className="rounded-xl border border-amber-300/30 bg-amber-400/10 p-3 text-xs text-amber-100">
          <p className="mb-1 flex items-center gap-1 font-semibold">
            <Info size={13} /> Partial data
          </p>
          <ul className="list-disc space-y-0.5 pl-4">
            {report.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <OfficialCard report={report} />
      {FEATURES.voice && <VoiceButton report={report} insights={insights} voice={voice} />}

      <div className="grid gap-3 md:grid-cols-2">
        <Card title="Water feel · swimming" icon={<Thermometer size={14} />} right={<CachedBadge cached={report.sea_temp.current.receipt.cached} />}>
          <FeelGauge feel={report.feel} sst={report.sea_temp} />
          <p className="mt-3 text-xs text-slate-400">{report.sea_temp.caveat}</p>
          {report.sea_temp.current.receipt.observed_at && (
            <p className="text-xs text-slate-400">Observed {fmtTime(report.sea_temp.current.receipt.observed_at)}</p>
          )}
          {verdicts?.ok && verdicts.data && (
            <p className="mt-2 rounded-lg bg-teal-400/10 p-2 text-sm text-teal-50">
              <Sparkles size={12} className="mr-1 inline" />
              <strong>{verdicts.data.swim_feel.verdict}</strong> {verdicts.data.swim_feel.reason}
            </p>
          )}
          {verdicts && !verdicts.ok && <GemmaUnavailable result={verdicts} />}
        </Card>
        <Card title="Water feel · cliff jumping" icon={<Mountain size={14} />}>
          <JumpMeter feel={report.feel} />
          {verdicts?.ok && verdicts.data && (
            <p className="mt-2 rounded-lg bg-teal-400/10 p-2 text-sm text-teal-50">
              <Sparkles size={12} className="mr-1 inline" />
              <strong>{verdicts.data.jump_feel.verdict}</strong> {verdicts.data.jump_feel.reason}
            </p>
          )}
        </Card>
      </div>

      <Card title="Chlorophyll-a · 7-day trend" icon={<Droplets size={14} />} right={<CachedBadge cached={chl.current.receipt.cached} />}>
        <div className="flex items-end justify-between gap-3">
          <div>
            <ReceiptButton receipt={chl.current.receipt}>
              <span className="text-4xl font-bold text-white">{chl.current.display}</span>
              {chl.current.value !== null && <span className="ml-1 text-sm text-slate-300">mg/m³</span>}
            </ReceiptButton>
            <p className="text-xs tracking-wide text-slate-400 uppercase">
              Level: {chl.level} · trend: {chl.trend_direction}
            </p>
            {chl.current.receipt.observed_at && (
              <p className={`text-xs ${chl.stale ? 'font-semibold text-amber-300' : 'text-slate-400'}`}>
                Observed {fmtTime(chl.current.receipt.observed_at)}
                {chl.age_days !== null && ` · ${chl.age_days.toFixed(1)} days old`}
                {chl.stale && ' · stale'}
              </p>
            )}
          </div>
        </div>
        <div className="mt-2">
          <ChlTrend trend={chl.trend} />
        </div>
        <p className="mt-2 text-xs text-slate-400">{chl.caveat}</p>
      </Card>

      <Card
        title={`Best time · ${report.best_time.day_label}`}
        icon={<Sun size={14} />}
        right={
          report.best_time.tide_receipt ? (
            <ReceiptButton receipt={report.best_time.tide_receipt} className="text-xs text-slate-400">
              <Waves size={12} className="mr-1 inline" />
              Tide: {report.best_time.tide_station?.name ?? 'Unavailable'}
            </ReceiptButton>
          ) : null
        }
      >
        <BestTimeStrip best={report.best_time} />
        {report.best_time.note && <p className="mt-2 text-xs text-slate-400">{report.best_time.note}</p>}
        <div className="mt-3 space-y-2">
          {report.best_time.windows.length === 0 && <p className="text-sm text-slate-400">No window available.</p>}
          {report.best_time.windows.map((w, i) => (
            <div key={w.start} className="window-glow rounded-xl bg-teal-400/10 p-2.5 text-sm">
              <p className="font-semibold text-teal-50">{w.label}</p>
              <p className="text-xs text-slate-300">{w.facts.join(' · ')}</p>
              {best?.ok && best.data?.windows[i] && (
                <p className="mt-1 text-xs text-teal-100">
                  <Sparkles size={11} className="mr-1 inline" />
                  {best.data.windows[i].reason}
                </p>
              )}
            </div>
          ))}
          {best && !best.ok && <GemmaUnavailable result={best} />}
          {report.best_time.weather_receipt && (
            <ReceiptButton receipt={report.best_time.weather_receipt} className="text-xs text-slate-400">
              Air temperature and sky: NWS hourly forecast
            </ReceiptButton>
          )}
        </div>
      </Card>

      {FEATURES.gemma && <ExplainCard insights={insights} loading={insightsLoading} error={insightsError} />}
    </div>
  )
}
