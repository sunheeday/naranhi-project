import { NextResponse, type NextRequest } from 'next/server'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { isDemoCameraEnabled } from '@/lib/test-entry-bypass'

interface RequestBody {
  message?: unknown
}

export async function POST(request: NextRequest) {
  const supabase = await createSupabaseServerClient()
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser()
  if ((authError || !user) && !isDemoCameraEnabled()) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const body = (await request.json().catch(() => null)) as RequestBody | null
  const message = typeof body?.message === 'string' ? body.message.trim() : ''
  if (!message) {
    return NextResponse.json({ ok: false, error: 'missing_message' }, { status: 400 })
  }

  const apiBase = (
    process.env.FASTAPI_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE_URL || ''
  )
    .trim()
    .replace(/\/+$/, '')

  if (!apiBase) {
    return NextResponse.json({ ok: false, error: 'missing_fastapi_url' }, { status: 503 })
  }

  const response = await fetch(`${apiBase}/notices/translate-text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_text: message,
      target_language: 'ko',
      translation_kind: 'message_to_ko',
    }),
    cache: 'no-store',
  })

  const result = await response.json().catch(() => null)
  if (!response.ok) {
    return NextResponse.json(
      { ok: false, error: result?.detail ?? result?.error ?? 'message_translation_failed' },
      { status: response.status },
    )
  }

  return NextResponse.json({
    ok: true,
    translatedText:
      result?.pipeline_result?.final_translation ?? result?.translation ?? '',
  })
}
