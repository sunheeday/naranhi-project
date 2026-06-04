import type { NextRequest } from 'next/server'

export function publicOrigin(request: NextRequest): string {
  const forwardedHost = request.headers.get('x-forwarded-host')
  const host = forwardedHost ?? request.headers.get('host')
  if (!host) {
    return process.env.NEXT_PUBLIC_SITE_URL ?? new URL(request.url).origin
  }

  const forwardedProto = request.headers.get('x-forwarded-proto') ?? 'https'
  return `${forwardedProto}://${host}`
}
