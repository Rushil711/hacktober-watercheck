import type {
  AppConfig,
  BeachReport,
  Health,
  Insights,
  NaturalSearchResult,
  NearbyResult,
  SearchResult,
} from './types'

let offline = false

export function setOffline(value: boolean) {
  offline = value
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function withOffline(path: string): string {
  if (!offline) return path
  return path + (path.includes('?') ? '&' : '?') + 'offline=1'
}

async function parseError(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status})`
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') message = body.detail
    else if (typeof body.error === 'string') message = body.error
  } catch {
    // keep the generic message
  }
  return new ApiError(res.status, message)
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(withOffline(path), { signal })
  if (!res.ok) throw await parseError(res)
  return res.json() as Promise<T>
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(withOffline(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) throw await parseError(res)
  return res.json() as Promise<T>
}

const q = (params: Record<string, string | number>) =>
  new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString()

export const api = {
  health: () => getJson<Health>('/api/health'),
  config: () => getJson<AppConfig>('/api/config'),
  search: (query: string, signal?: AbortSignal) => getJson<SearchResult>(`/api/search?${q({ q: query })}`, signal),
  report: (spot: { lat: number; lon: number; name: string; kind: string }, signal?: AbortSignal) =>
    getJson<BeachReport>(`/api/beach/report?${q(spot)}`, signal),
  nearby: (lat: number, lon: number, driveMin: number, signal?: AbortSignal) =>
    getJson<NearbyResult>(`/api/nearby?${q({ lat, lon, drive_min: driveMin })}`, signal),
  insights: (report: BeachReport, signal?: AbortSignal) => postJson<Insights>('/api/beach/insights', report, signal),
  naturalSearch: (query: string, origin: { lat: number; lon: number } | null, signal?: AbortSignal) =>
    postJson<NaturalSearchResult>('/api/gemma/search', { query, origin }, signal),
  voiceStatus: () => getJson<{ configured: boolean; problem: string | null; docs_url: string }>('/api/voice/status'),
  voiceBriefing: async (report: BeachReport, insights: Insights | null): Promise<Blob> => {
    const res = await fetch(withOffline('/api/voice/briefing'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report, explanation: insights?.explain.ok ? insights.explain.data : null }),
    })
    if (!res.ok) throw await parseError(res)
    return res.blob()
  },
}

export function tileUrl(provider: 'base' | 'gibs' | 'chl', extra = ''): string {
  return withOffline(`/api/tiles/${provider}/{z}/{x}/{y}${extra}`)
}
