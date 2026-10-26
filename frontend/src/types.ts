import type { Geometry } from 'geojson'

export type OfficialStatusCode =
  | 'closure'
  | 'warning'
  | 'advisory'
  | 'no_advisory_found'
  | 'unverified'
  | 'unavailable'
export type HaloColor = 'green' | 'amber' | 'coral'

export interface Receipt {
  source: string
  dataset?: string | null
  observed_at?: string | null
  fetched_at?: string | null
  url?: string | null
  cached: boolean
  note?: string | null
}

export interface Measurement {
  label: string
  value: number | null
  unit: string | null
  display: string
  receipt: Receipt
}

export interface Spot {
  name: string
  lat: number
  lon: number
  kind: string
}

export interface TrendPoint {
  date: string
  value: number | null
  pixels: number
}

export interface ChlorophyllBlock {
  current: Measurement
  trend: TrendPoint[]
  trend_direction: string
  level: 'typical' | 'elevated' | 'high' | 'unknown'
  age_days: number | null
  stale: boolean
  pixels_used: number
  caveat: string
}

export interface SeaTempBlock {
  current: Measurement
  celsius: number | null
  age_days: number | null
  stale: boolean
  caveat: string
}

export interface OfficialEvent {
  type: string
  issued_at: string | null
  description: string | null
}

export interface Station {
  id: string | null
  name: string
  distance_km: number
}

export interface OfficialStatus {
  status: OfficialStatusCode
  label: string
  detail: string
  station: Station | null
  events: OfficialEvent[]
  receipt: Receipt
}

export interface Imagery {
  date: string | null
  layer: string
  tile_url_template: string | null
  max_zoom: number
  fallback_used: boolean
  receipt: Receipt
}

export interface HourPoint {
  time: string
  hour_label: string
  tide_ft: number | null
  air_f: number | null
  is_daytime: boolean | null
  sky: string | null
  in_window: boolean
}

export interface TimeWindow {
  start: string
  end: string
  label: string
  score: number
  facts: string[]
}

export interface BestTime {
  day_label: string
  hours: HourPoint[]
  windows: TimeWindow[]
  tide_station: Station | null
  tide_receipt: Receipt | null
  weather_receipt: Receipt | null
  note: string | null
}

export interface Feel {
  swim_level: string
  swim_label: string
  jump_level: string
  jump_label: string
  wetsuit: string | null
  gauge_position: number | null
  jump_meter: number | null
  tide_now_ft: number | null
  safety_line: string
}

export interface Halo {
  color: HaloColor
  label: string
  icon: string
  reasons: string[]
}

export interface BeachReport {
  spot: Spot
  generated_at: string
  offline: boolean
  chlorophyll: ChlorophyllBlock
  sea_temp: SeaTempBlock
  official: OfficialStatus
  imagery: Imagery
  best_time: BestTime
  feel: Feel
  halo: Halo
  data_age: string
  warnings: string[]
}

export interface Candidate {
  name: string
  lat: number
  lon: number
  kind: string
  distance_km: number
  source: string
}

export interface SearchResult {
  query: string
  place: Candidate | null
  candidates: Candidate[]
  attribution: string
  warnings: string[]
}

export interface WaterBody {
  id: string
  name: string
  kind: string // beach, bay, river, lake, reservoir, estuary, or lagoon
  lat: number
  lon: number
  distance_km: number // to the nearest point of the outline
  source: string
  geometry: Geometry
  report_available: boolean // the ocean report covers beaches and bays only
  halo: Halo | null
  official_status: OfficialStatusCode | null
  sea_temp_f: number | null
  chl: number | null
}

export interface NearbyResult {
  origin: Spot
  radius_km: number
  spots: WaterBody[]
  attribution: string
  warnings: string[]
}

export interface AppConfig {
  demo_beaches: { key: string; name: string; lat: number; lon: number; kind: string }[]
  nearby_default_mi: number
  nearby_min_mi: number
  nearby_max_mi: number
  chl_dataset: string
  chl_variable: string
  chl_wms_url: string
  chl_wms_layer: string
  gibs_layer: string
  gibs_max_zoom: number
  safety_line: string
}

export interface Health {
  ok: boolean
  offline: boolean
  demo_mode: boolean
  gemma_configured: boolean
  gemma_model: string
  voice_configured: boolean
}

export interface SkillResult<T> {
  ok: boolean
  data: T | null
  error: string | null
  attempts: number
  model: string | null
  cached: boolean
}

export interface Explanation {
  headline: string
  environmental_summary: string
  key_observations: string[]
  concerns: string[]
  limitations: string[]
  recommended_next_steps: string[]
  sources_used: string[]
}

export interface FeelVerdict {
  level: string
  verdict: string
  reason: string
}

export interface Verdicts {
  swim_feel: FeelVerdict
  jump_feel: FeelVerdict
}

export interface BestHoursOut {
  windows: { label: string; reason: string }[]
}

export interface Insights {
  explain: SkillResult<Explanation>
  verdicts: SkillResult<Verdicts>
  best_hours: SkillResult<BestHoursOut>
}

export interface NaturalFilter {
  max_drive_min: number
  min_temp_f: number | null
  activity: 'swim' | 'jump' | 'any'
  near: string | null
}

export interface NaturalSearchResult {
  filter: SkillResult<NaturalFilter>
  origin: Spot | null
  result: NearbyResult | null
  warnings: string[]
}
