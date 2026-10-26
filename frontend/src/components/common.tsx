import { AnimatePresence, motion } from 'framer-motion'
import { CircleCheck, CircleHelp, ExternalLink, LoaderCircle, OctagonAlert, TriangleAlert, X } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { fmtTime } from '../format'
import { theme } from '../theme'
import type { Halo, Receipt } from '../types'

export function CachedBadge({ cached }: { cached: boolean }) {
  if (!cached) return null
  return (
    <span className="rounded-full bg-amber-400/20 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-amber-200 uppercase">
      Cached
    </span>
  )
}

export function ReceiptButton({ receipt, children, className = '' }: { receipt: Receipt; children: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <span ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`cursor-pointer rounded-md text-left underline decoration-teal-300/40 decoration-dotted underline-offset-4 hover:decoration-teal-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-300 ${className}`}
        aria-expanded={open}
        title="Show evidence receipt"
      >
        {children}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.15 }}
            className="glass-strong absolute top-full left-0 z-[1200] mt-2 w-80 rounded-xl p-3 text-xs text-slate-200 shadow-2xl"
            role="dialog"
            aria-label="Evidence receipt"
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] font-semibold tracking-widest text-teal-200 uppercase">Evidence receipt</span>
              <button type="button" onClick={() => setOpen(false)} className="text-slate-400 hover:text-white" aria-label="Close">
                <X size={14} />
              </button>
            </div>
            <dl className="grid grid-cols-[88px_1fr] gap-x-2 gap-y-1">
              <dt className="text-slate-400">Source</dt>
              <dd>{receipt.source}</dd>
              <dt className="text-slate-400">Dataset</dt>
              <dd className="break-words">{receipt.dataset ?? 'Unavailable'}</dd>
              <dt className="text-slate-400">Observed</dt>
              <dd>{receipt.observed_at ? fmtTime(receipt.observed_at) : 'Unavailable'}</dd>
              <dt className="text-slate-400">Fetched</dt>
              <dd className="flex items-center gap-1.5">
                {fmtTime(receipt.fetched_at)} <CachedBadge cached={receipt.cached} />
              </dd>
              {receipt.note && (
                <>
                  <dt className="text-slate-400">Note</dt>
                  <dd>{receipt.note}</dd>
                </>
              )}
            </dl>
            {receipt.url ? (
              <a
                href={receipt.url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-teal-300 hover:text-teal-100"
              >
                Open source <ExternalLink size={12} />
              </a>
            ) : (
              <p className="mt-2 text-slate-500">No link available.</p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </span>
  )
}

export function HaloIcon({ icon, size = 16 }: { icon: string; size?: number }) {
  if (icon === 'octagon-alert') return <OctagonAlert size={size} />
  if (icon === 'triangle-alert') return <TriangleAlert size={size} />
  if (icon === 'circle-check') return <CircleCheck size={size} />
  return <CircleHelp size={size} />
}

export function HaloBadge({ halo }: { halo: Halo }) {
  const color = theme.halo[halo.color]
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
      style={{ background: `${color}26`, color, boxShadow: `0 0 16px ${color}55` }}
      title={halo.reasons.join(' · ')}
    >
      <HaloIcon icon={halo.icon} size={14} />
      {halo.label}
    </span>
  )
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-teal-100/80" role="status">
      <LoaderCircle className="animate-spin" size={18} /> {label}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-white/15 p-4 text-sm text-slate-300">
      <p className="font-medium text-slate-100">{title}</p>
      {children && <div className="mt-1 text-slate-400">{children}</div>}
    </div>
  )
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-rose-400/40 bg-rose-500/10 p-4 text-sm text-rose-100" role="alert">
      <p className="font-medium">Something went wrong</p>
      <p className="mt-1 text-rose-200/80">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-2 rounded-lg bg-rose-400/20 px-3 py-1 text-xs hover:bg-rose-400/30">
          Try again
        </button>
      )}
    </div>
  )
}

export function Card({ title, icon, children, right }: { title: string; icon?: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="glass card-lift rounded-2xl p-4">
      <header className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-[family-name:var(--font-display)] text-[17px] font-semibold text-white [&>svg]:text-teal-300">
          {icon}
          {title}
        </h3>
        {right}
      </header>
      {children}
    </section>
  )
}
