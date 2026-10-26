export function fmtTime(iso?: string | null): string {
  if (!iso) return 'Unavailable'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
}

export function kmToMi(km: number): string {
  const mi = km / 1.609344
  return mi < 10 ? mi.toFixed(1) : String(Math.round(mi))
}
