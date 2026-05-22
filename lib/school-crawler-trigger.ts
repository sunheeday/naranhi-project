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

export async function triggerInitialSchoolCrawl(schoolId: string): Promise<boolean> {
  return postCrawlerApi(`/crawler/schools/${encodeURIComponent(schoolId)}/discover-board`, 'Initial school crawler')
}

export async function triggerPendingSchoolExtraction(schoolId: string, maxNotices?: number): Promise<boolean> {
  const query = maxNotices ? `?max_notices=${encodeURIComponent(String(maxNotices))}` : ''
  return postCrawlerApi(`/crawler/schools/${encodeURIComponent(schoolId)}/extract-pending${query}`, 'Initial content extractor')
}

async function postCrawlerApi(path: string, label: string): Promise<boolean> {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/+$/, '')
  if (!apiBase) return false

  const headers: Record<string, string> = {}
  const token = process.env.CRAWLER_INTERNAL_TOKEN?.trim()
  if (token) {
    headers['X-Internal-Token'] = token
  }

  try {
    const response = await fetch(`${apiBase}${path}`, {
      method: 'POST',
      headers,
      cache: 'no-store',
    })
    if (!response.ok) {
      console.warn(`${label} failed with HTTP ${response.status}`)
      return false
    }
    return true
  } catch (error) {
    console.warn(`${label} request failed`, error)
    return false
  }
}
