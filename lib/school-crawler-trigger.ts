import 'server-only'

export interface SchoolCrawlerState {
  id: string
  crawl_status: string | null
  crawl_board_url: string | null
  crawl_last_checked_at: string | null
}

const RETRYABLE_INITIAL_CRAWL_STATUSES = new Set([
  'pending',
  'internal_error',
  'fetch_timeout',
  'fetch_unavailable',
  'homepage_missing',
])

export function schoolNeedsInitialCrawl(school: SchoolCrawlerState): boolean {
  if (school.crawl_board_url) return false
  if (!school.crawl_last_checked_at) return true
  return RETRYABLE_INITIAL_CRAWL_STATUSES.has(school.crawl_status ?? 'pending')
}

export async function triggerInitialSchoolCrawl(schoolId: string): Promise<void> {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/+$/, '')
  if (!apiBase) return

  const headers: Record<string, string> = {}
  const token = process.env.CRAWLER_INTERNAL_TOKEN?.trim()
  if (token) {
    headers['X-Internal-Token'] = token
  }

  try {
    const response = await fetch(
      `${apiBase}/crawler/schools/${encodeURIComponent(schoolId)}/discover-board`,
      {
        method: 'POST',
        headers,
        cache: 'no-store',
      }
    )
    if (!response.ok) {
      console.warn(`Initial school crawler failed with HTTP ${response.status}`)
    }
  } catch (error) {
    console.warn('Initial school crawler request failed', error)
  }
}
