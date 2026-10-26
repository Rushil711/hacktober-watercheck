import { motion } from 'framer-motion'
import { Shirt, ShieldAlert } from 'lucide-react'
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { theme } from '../theme'
import type { BestTime, Feel, SeaTempBlock, TrendPoint } from '../types'
import { ReceiptButton } from './common'

export function FeelGauge({ feel, sst }: { feel: Feel; sst: SeaTempBlock }) {
  const pos = feel.gauge_position
  const angle = Math.PI * (1 - (pos ?? 0))
  const cx = 110
  const cy = 104
  const r = 84
  const mx = cx + r * Math.cos(angle)
  const my = cy - r * Math.sin(angle)
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 220 120" className="w-full max-w-[260px]" role="img" aria-label={`Water feel gauge: ${feel.swim_label}`}>
        <defs>
          <linearGradient id="feelGrad" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#60a5fa" />
            <stop offset="45%" stopColor="#2dd4bf" />
            <stop offset="75%" stopColor="#fbbf24" />
            <stop offset="100%" stopColor="#fb7185" />
          </linearGradient>
        </defs>
        <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} stroke="rgba(255,255,255,0.12)" strokeWidth="16" fill="none" strokeLinecap="round" />
        <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} stroke="url(#feelGrad)" strokeWidth="10" fill="none" strokeLinecap="round" />
        {pos !== null && (
          <motion.circle
            initial={{ cx: cx - r, cy }}
            animate={{ cx: mx, cy: my }}
            transition={{ type: 'spring', stiffness: 60, damping: 14 }}
            r="9"
            fill="#fff"
            stroke="#06142b"
            strokeWidth="3"
          />
        )}
        <text x={cx - r} y={cy + 16} fill="#93c5fd" fontSize="11" textAnchor="middle">
          Brr
        </text>
        <text x={cx + r} y={cy + 16} fill="#fda4af" fontSize="11" textAnchor="middle">
          Warm
        </text>
      </svg>
      <div className="-mt-10 text-center">
        <ReceiptButton receipt={sst.current.receipt}>
          <span className="text-5xl font-bold tracking-tight text-white">{sst.current.display}</span>
          {sst.current.value !== null && <span className="ml-1 text-lg text-slate-300">°F</span>}
        </ReceiptButton>
        <p className="text-xs tracking-wide text-slate-400 uppercase">Satellite sea surface temp</p>
      </div>
      <div className="mt-2 flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-xs text-slate-200">
        <Shirt size={14} className="text-teal-300" />
        Wetsuit: <strong>{feel.wetsuit ?? 'Unavailable'}</strong>
      </div>
    </div>
  )
}

export function JumpMeter({ feel }: { feel: Feel }) {
  const pct = feel.jump_meter
  return (
    <div className="flex items-stretch gap-4">
      <div
        className="relative h-36 w-7 overflow-hidden rounded-full bg-white/10"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
        aria-label="Jump meter"
      >
        <motion.div
          className="absolute bottom-0 left-0 w-full rounded-full"
          style={{ background: `linear-gradient(0deg, ${theme.tide}, ${theme.teal})` }}
          initial={{ height: 0 }}
          animate={{ height: `${pct ?? 0}%` }}
          transition={{ duration: 0.9, ease: 'easeOut' }}
        />
      </div>
      <div className="flex flex-1 flex-col justify-between">
        <div>
          <p className="text-4xl font-bold text-white">{pct === null ? 'Unavailable' : `${pct}`}</p>
          <p className="text-xs tracking-wide text-slate-400 uppercase">Jump meter (water feel + tide)</p>
          <p className="mt-2 text-sm text-slate-200">{feel.jump_label}</p>
          <p className="text-xs text-slate-400">
            Tide now: {feel.tide_now_ft === null ? 'Unavailable' : `${feel.tide_now_ft.toFixed(1)} ft MLLW`}
          </p>
        </div>
        <p className="mt-3 flex items-start gap-1.5 rounded-lg bg-amber-400/10 p-2 text-xs text-amber-100">
          <ShieldAlert size={14} className="mt-0.5 shrink-0" />
          {feel.safety_line}
        </p>
      </div>
    </div>
  )
}

export function BestTimeStrip({ best }: { best: BestTime }) {
  const data = best.hours.map((h) => ({ ...h, label: h.hour_label }))
  const hasData = data.some((d) => d.tide_ft !== null || d.air_f !== null)
  if (!hasData) return <p className="text-sm text-slate-400">Tide and forecast data are unavailable.</p>
  const windowRanges = best.windows.map((w) => {
    const idx = data.findIndex((d) => d.time === w.start)
    return idx >= 0 ? { x1: data[idx].label, x2: data[Math.min(idx + 1, data.length - 1)].label } : null
  })
  return (
    <div>
      <div className="h-36">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 6, right: 4, left: -18, bottom: 0 }}>
            <defs>
              <linearGradient id="tideFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={theme.tide} stopOpacity={0.55} />
                <stop offset="100%" stopColor={theme.tide} stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 10 }} interval={3} />
            <YAxis yAxisId="tide" tick={{ fill: '#7dd3fc', fontSize: 10 }} unit="ft" />
            <YAxis yAxisId="air" orientation="right" tick={{ fill: '#fcd34d', fontSize: 10 }} unit="°" domain={['dataMin - 4', 'dataMax + 4']} />
            <Tooltip
              contentStyle={{ background: '#0b2244', border: '1px solid rgba(153,246,228,0.2)', borderRadius: 10, fontSize: 12 }}
              formatter={(value, name) => [value ?? 'Unavailable', name === 'tide_ft' ? 'Tide (ft)' : 'Air (°F)']}
            />
            {windowRanges.map(
              (r, i) =>
                r && <ReferenceArea key={i} yAxisId="tide" x1={r.x1} x2={r.x2} fill={theme.teal} fillOpacity={0.22} stroke={theme.teal} strokeOpacity={0.8} />,
            )}
            <Area yAxisId="tide" type="monotone" dataKey="tide_ft" stroke={theme.tide} fill="url(#tideFill)" strokeWidth={2} connectNulls />
            <Line yAxisId="air" type="monotone" dataKey="air_f" stroke={theme.air} dot={false} strokeWidth={2} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 grid grid-cols-24 gap-[2px]" aria-hidden>
        {best.hours.map((h) => (
          <div
            key={h.time}
            title={`${h.hour_label}${h.is_daytime ? ' · daylight' : ''}`}
            className={`h-2.5 rounded-sm ${h.in_window ? 'window-glow bg-teal-300' : h.is_daytime ? 'bg-amber-200/40' : 'bg-white/10'}`}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-slate-400">
        <span>12 AM</span>
        <span>Daylight shown in sand, best window glows</span>
        <span>11 PM</span>
      </div>
    </div>
  )
}

export function ChlTrend({ trend }: { trend: TrendPoint[] }) {
  const data = trend.map((t) => ({ ...t, day: t.date.slice(5) }))
  const any = data.some((d) => d.value !== null)
  return (
    <div className="h-24">
      {any ? (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 0, left: -24, bottom: 0 }}>
            <XAxis dataKey="day" tick={{ fill: '#94a3b8', fontSize: 10 }} />
            <YAxis tick={{ fill: '#86efac', fontSize: 10 }} />
            <Tooltip
              contentStyle={{ background: '#0b2244', border: '1px solid rgba(153,246,228,0.2)', borderRadius: 10, fontSize: 12 }}
              formatter={(value) => [value === null ? 'No clear pixels' : `${value} mg/m³`, 'Chlorophyll']}
            />
            <Bar dataKey="value" fill={theme.chl} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className="grid h-full place-items-center rounded-lg border border-dashed border-white/10 text-center text-xs text-slate-400">
          No cloud-free satellite pixels in the last 7 days
        </div>
      )}
    </div>
  )
}
