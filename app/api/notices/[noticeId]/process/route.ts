import { cookies } from 'next/headers'
import { NextResponse, type NextRequest } from 'next/server'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'

interface RouteContext {
  params: Promise<{ noticeId: string }>
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { noticeId } = await context.params
  if (!noticeId) {
    return NextResponse.json({ ok: false, error: 'missing_notice_id' }, { status: 400 })
  }

  const supabase = await createSupabaseServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const { data: notice } = await supabase
    .from('notices')
    .select('id, status')
    .eq('id', noticeId)
    .maybeSingle()

  if (!notice) {
    return NextResponse.json({ ok: false, error: 'notice_not_found' }, { status: 404 })
  }

  if (notice.status === 'done') {
    return NextResponse.json({ ok: true, skipped: true, status: notice.status })
  }

  const targetLanguage = await resolveTargetLanguage(request, user.id)
  const apiBase = (
    process.env.FASTAPI_INTERNAL_URL
    || process.env.NEXT_PUBLIC_API_BASE_URL
    || ''
  ).trim().replace(/\/+$/, '')

  if (!apiBase) {
    return NextResponse.json({ ok: false, error: 'missing_fastapi_url' }, { status: 503 })
  }

  const response = await fetch(`${apiBase}/notices/${encodeURIComponent(noticeId)}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_language: targetLanguage }),
    cache: 'no-store',
  })

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    return NextResponse.json(
      { ok: false, error: body?.detail ?? body?.error ?? 'notice_process_failed' },
      { status: response.status }
    )
  }

  return NextResponse.json({ ok: true, targetLanguage, result: body })
}

async function resolveTargetLanguage(request: NextRequest, userId: string): Promise<Locale> {
  const body = await request.json().catch(() => null)
  if (isValidLocale(body?.target_language)) {
    return body.target_language
  }

  const supabase = await createSupabaseServerClient()
  const { data: profile } = await supabase
    .from('profiles')
    .select('native_language, locale')
    .eq('id', userId)
    .maybeSingle()

  if (isValidLocale(profile?.native_language)) {
    return profile.native_language
  }
  if (isValidLocale(profile?.locale)) {
    return profile.locale
  }

  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  return isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
}
