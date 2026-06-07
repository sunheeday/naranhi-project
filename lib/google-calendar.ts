function compactIsoDate(isoDate: string): string {
  return isoDate.replace(/-/g, '')
}

function addDaysToIso(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  const utcMs = Date.UTC(year, month - 1, day)
  return new Date(utcMs + days * 86400000).toISOString().slice(0, 10)
}

export function buildGoogleCalendarEventUrl({
  title,
  isoDate,
  details,
  location,
}: {
  title: string
  isoDate: string
  details?: string | null
  location?: string | null
}): string {
  const endDateExclusive = addDaysToIso(isoDate, 1)
  const url = new URL('https://calendar.google.com/calendar/render')

  url.searchParams.set('action', 'TEMPLATE')
  url.searchParams.set('text', title)
  url.searchParams.set(
    'dates',
    `${compactIsoDate(isoDate)}/${compactIsoDate(endDateExclusive)}`,
  )

  if (details?.trim()) {
    url.searchParams.set('details', details.trim())
  }
  if (location?.trim()) {
    url.searchParams.set('location', location.trim())
  }

  return url.toString()
}
