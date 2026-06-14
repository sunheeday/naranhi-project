import { cookies } from 'next/headers'
import { NextResponse, type NextRequest } from 'next/server'
import { defaultLocale, isValidLocale, type Locale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { isTestEntryBypassEnabled } from '@/lib/test-entry-bypass'

export async function POST(request: NextRequest) {
  const testEntryBypass = isTestEntryBypassEnabled()
  const supabase = await createSupabaseServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if ((authError || !user) && !testEntryBypass) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const formData = await request.formData().catch(() => null)
  const file = formData?.get('file')
  if (!(file instanceof File)) {
    return NextResponse.json({ ok: false, error: 'missing_file' }, { status: 400 })
  }

  const apiBase = (
    process.env.FASTAPI_INTERNAL_URL
    || process.env.NEXT_PUBLIC_API_BASE_URL
    || ''
  ).trim().replace(/\/+$/, '')

  if (!apiBase) {
    return NextResponse.json({ ok: false, error: 'missing_fastapi_url' }, { status: 503 })
  }

  const targetLanguage = await resolveTargetLanguage(user?.id ?? null)
  const backendFormData = new FormData()
  backendFormData.append('file', file, file.name)

  const response = await fetch(
    `${apiBase}/capture/ocr?target_language=${encodeURIComponent(targetLanguage)}`,
    {
      method: 'POST',
      body: backendFormData,
      cache: 'no-store',
    }
  )

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    return NextResponse.json(
      { ok: false, error: body?.detail ?? body?.error ?? 'capture_ocr_failed' },
      { status: response.status }
    )
  }

  return NextResponse.json({
    ok: true,
    targetLanguage,
    extractedText: body?.extracted_text ?? '',
    ocr: body?.ocr ?? null,
    translation: body?.translation ?? null,
    translatedText: body?.translation?.translation ?? '',
  })
}

async function resolveTargetLanguage(userId: string | null): Promise<Locale> {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  if (isValidLocale(cookieLocale)) {
    return cookieLocale
  }

  if (!userId) {
    return defaultLocale
  }

  const supabase = await createSupabaseServerClient()
  const { data: profile } = await supabase
    .from('profiles')
    .select('native_language, locale')
    .eq('id', userId)
    .maybeSingle()

  if (isValidLocale(profile?.locale)) {
    return profile.locale
  }
  if (isValidLocale(profile?.native_language)) {
    return profile.native_language
  }

  return defaultLocale
}
