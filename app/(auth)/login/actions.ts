'use server'

import { createSupabaseServerClient } from '@/lib/supabase/server'
import { safeNextPath } from '@/lib/auth/redirect'
import { headers } from 'next/headers'
import { redirect } from 'next/navigation'

export async function signInWithGoogle(nextPath?: string | null) {
  const supabase = await createSupabaseServerClient()
  const headersList = await headers()
  const origin = _requestOrigin(headersList)
  if (!origin) {
    redirect('/login?error=oauth_failed')
  }

  const callbackUrl = new URL('/auth/callback', origin)
  const safeNext = safeNextPath(nextPath)
  if (safeNext !== '/') {
    callbackUrl.searchParams.set('next', safeNext)
  }

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: callbackUrl.toString(),
      queryParams: {
        prompt: 'select_account',
      },
    },
  })

  if (error || !data.url) {
    redirect('/login?error=oauth_failed')
  }

  redirect(data.url)
}

function _requestOrigin(headersList: Headers): string | null {
  const origin = headersList.get('origin')
  if (origin) return origin

  const forwardedHost = headersList.get('x-forwarded-host')
  const host = forwardedHost ?? headersList.get('host')
  if (!host) return process.env.NEXT_PUBLIC_SITE_URL ?? null

  const forwardedProto = headersList.get('x-forwarded-proto') ?? 'https'
  return `${forwardedProto}://${host}`
}
