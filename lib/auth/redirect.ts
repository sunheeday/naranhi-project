export const DEFAULT_SIGNED_IN_PATH = '/'

export function safeNextPath(value: string | null | undefined): string {
  if (!value) return DEFAULT_SIGNED_IN_PATH

  let decoded = value
  try {
    decoded = decodeURIComponent(value)
  } catch {
    decoded = value
  }

  if (!decoded.startsWith('/') || decoded.startsWith('//') || decoded.includes('\\')) {
    return DEFAULT_SIGNED_IN_PATH
  }

  return decoded
}

export function appendNextParam(path: string, next: string): string {
  const url = new URL(path, 'http://naranhi.local')
  const safeNext = safeNextPath(next)
  if (safeNext !== DEFAULT_SIGNED_IN_PATH) {
    url.searchParams.set('next', safeNext)
  }
  return `${url.pathname}${url.search}`
}
