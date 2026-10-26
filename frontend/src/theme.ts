import type { HaloColor, OfficialStatusCode } from './types'

export const theme = {
  navy: '#06142b',
  navySoft: '#0b2244',
  teal: '#2dd4bf',
  tealSoft: '#99f6e4',
  halo: {
    green: '#34d399',
    amber: '#fbbf24',
    coral: '#fb7185',
  } satisfies Record<HaloColor, string>,
  tide: '#38bdf8',
  air: '#fbbf24',
  chl: '#4ade80',
  water: '#38bdf8',
  waterLine: '#7dd3fc',
  sand: '#f5deb3', // pale, so beaches do not look like an amber halo
}

// Map and list color for a water body kind from /api/nearby.
export function kindColor(kind: string): string {
  return kind === 'beach' ? theme.sand : theme.water
}

export const officialStyle: Record<OfficialStatusCode, { tone: string; ring: string; note?: string }> = {
  closure: { tone: 'text-rose-200 bg-rose-500/20', ring: 'ring-rose-400/60' },
  warning: { tone: 'text-rose-200 bg-rose-500/20', ring: 'ring-rose-400/60' },
  advisory: { tone: 'text-rose-100 bg-rose-500/15', ring: 'ring-rose-300/50' },
  no_advisory_found: {
    tone: 'text-teal-100 bg-teal-500/10',
    ring: 'ring-teal-300/40',
    note: 'Not the same as confirmed safe.',
  },
  unverified: {
    tone: 'text-slate-200 bg-slate-500/15',
    ring: 'ring-slate-400/40 ring-dashed',
    note: 'No matching official station. Check posted signs.',
  },
  unavailable: { tone: 'text-slate-300 bg-slate-600/20', ring: 'ring-slate-500/40', note: 'Official service did not respond.' },
}
